"""Adapter for World Dai Star: Yume no Stellarium (Yumesute)."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from core.base import (
    CategoryResult,
    DownloadOptions,
    DownloadTask,
    GameAdapter,
    sanitize_filename,
)
from core.http_client import fetch_bytes, load_or_fetch_json, run_download_tasks
from core.unity_utils import extract_animated_card_bundle, extract_textures_and_texts

SIRIUS_RAW = "https://raw.githubusercontent.com/SonolusHaniwa/sirius-decrypted-data/main"
ADV_RAW = "https://raw.githubusercontent.com/wds-sirius/Adv-Resource/main"
CONFIG_YML = "https://raw.githubusercontent.com/wds-sirius/asset-of-dreams/main/config.yml"
CDN_2D = "https://assets-e.wds-stellarium.com/production/2d-assets/Android"


class YumesuteAdapter(GameAdapter):
    code = "yumesute"
    name = "World Dai Star: Yume no Stellarium (Yumesute)"
    credits = "wds-sirius (Adv-Resource / asset-of-dreams), SonolusHaniwa/sirius-decrypted-data & WDS Live CDN"
    supported_regions = ("jp",)
    supports_card_animation = True

    _CARD_RARITY_MAP = {"1": 1, "n": 1, "2": 2, "r": 2, "3": 3, "sr": 3, "4": 4, "ssr": 4}
    _POSTER_RARITY_MAP = {"r": "R", "2": "R", "sr": "SR", "3": "SR", "ssr": "SSR", "4": "SSR", "ur": "UR"}

    def _load_masterdata(self, options: DownloadOptions):
        mdir = self.masterdata_dir(options)
        cards = load_or_fetch_json(
            mdir / "card.json",
            f"{SIRIUS_RAW}/card.json",
            refresh=options.refresh_masterdata,
        )
        char_bases = load_or_fetch_json(
            mdir / "CharacterBaseMaster.json",
            f"{SIRIUS_RAW}/master/CharacterBaseMaster.json",
            refresh=options.refresh_masterdata,
        )
        posters = load_or_fetch_json(
            mdir / "PosterMaster.json",
            f"{SIRIUS_RAW}/master/PosterMaster.json",
            refresh=options.refresh_masterdata,
        )
        spines = load_or_fetch_json(
            mdir / "Spine.json",
            f"{ADV_RAW}/manifest/Spine.json",
            refresh=options.refresh_masterdata,
        )
        base_by_id = {c["Id"]: c for c in char_bases if "Id" in c}
        return cards, char_bases, base_by_id, posters, spines

    def _get_asset_version(self, options: DownloadOptions) -> str:
        cache_path = self.masterdata_dir(options) / "asset_version.txt"
        if not options.refresh_masterdata and cache_path.exists():
            val = cache_path.read_text(encoding="utf-8").strip()
            if val:
                return val
        try:
            text = fetch_bytes(CONFIG_YML, timeout=30).decode("utf-8", "ignore")
            m = re.search(r'asset_version:\s*["\']?([0-9.]+)["\']?', text)
            if m:
                ver = m.group(1)
                cache_path.write_text(ver, encoding="utf-8")
                return ver
        except Exception:
            pass
        return "1.96.0"

    def _load_2dcatalog_groups(
        self, options: DownloadOptions, ver: str | None = None
    ) -> dict[str, list[str]]:
        mdir = self.masterdata_dir(options)
        ver = ver or self._get_asset_version(options)
        live_cache = mdir / f"2dcatalog_{ver}.json"

        cat: dict[str, Any] | None = None
        if not options.refresh_masterdata and live_cache.exists() and live_cache.stat().st_size > 0:
            cat = json.loads(live_cache.read_text(encoding="utf-8"))
        else:
            try:
                import brotli

                raw_br = fetch_bytes(
                    f"{CDN_2D}/{ver}/catalog_{ver}.json.br",
                    timeout=60,
                    retries=4,
                    reject_html=True,
                )
                decoded = brotli.decompress(raw_br).decode("utf-8")
                cat = json.loads(decoded)
                tmp = live_cache.with_suffix(".json.part")
                tmp.write_text(decoded, encoding="utf-8")
                tmp.replace(live_cache)
            except Exception:
                cat = None

        if cat is None:
            cat = load_or_fetch_json(
                mdir / "2dcatalog.json",
                f"{ADV_RAW}/_temp/2dcatalog.json",
                refresh=options.refresh_masterdata,
            )

        prefixes = cat.get("m_InternalIdPrefixes", [])
        rx = re.compile(r"^(\d+)#(.*)$")
        groups: dict[str, list[str]] = {}
        seen: set[str] = set()
        for iid in cat.get("m_InternalIds", []):
            if not isinstance(iid, str) or not iid.endswith(".bundle"):
                continue
            m = rx.match(iid)
            resolved = prefixes[int(m.group(1))] + m.group(2) if m and int(m.group(1)) < len(prefixes) else iid
            parts = resolved.split("://", 1)[-1].split("/", 2)
            rel = parts[2] if len(parts) == 3 else resolved
            if rel in seen or "/" not in rel:
                continue
            seen.add(rel)
            grp = rel.split("/", 1)[0]
            groups.setdefault(grp, []).append(rel)
        return groups

    @staticmethod
    def _animated_card_bundles_by_cid(groups: dict[str, list[str]]) -> dict[str, list[str]]:
        """
        Return `{card_id: [bundle_rel, ...]}` for animated Actor Card bundles.
        Verified on live Unity bundles:
          - 4-star SSR awakened variants (`4xxxx_1.bundle`) include UIParticle + Holo Material + Mask + FX sheet
          - 5-star series (`15xxxx`, variants `_0.._3`) include UIParticle + layered depth textures + Holo Material
          - 1*/2*/3* and `4xxxx_0` only contain static 1920x1180 Texture2D prefabs
        """
        out: dict[str, list[str]] = {}
        for rel in sorted(groups.get("charactercards_assets_charactercard", [])):
            stem = Path(rel).stem
            if "_" not in stem:
                continue
            cid, suffix = stem.split("_", 1)
            if cid.startswith("15") or suffix != "0":
                out.setdefault(cid, []).append(rel)
        return out

    def _matched_base_ids(self, char_bases: list[dict], query: str) -> set[int]:
        q = query.strip().lower()
        out: set[int] = set()
        for ch in char_bases:
            cid = ch.get("Id")
            haystack = " ".join(
                str(x)
                for x in (
                    cid,
                    ch.get("Name", ""),
                    ch.get("NameRomanization", ""),
                    ch.get("FamilyName", ""),
                    ch.get("FirstName", ""),
                    ch.get("FamilyNameRomanization", ""),
                    ch.get("FirstNameRomanization", ""),
                )
            ).lower()
            if q in haystack or str(cid) == q:
                out.add(cid)
        return out

    def _filter_cards(
        self,
        cards: list[dict],
        char_bases: list[dict],
        options: DownloadOptions,
        animated_cids: set[str] | None = None,
    ) -> list[dict]:
        target_rar = self._CARD_RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()
        matched_ids = self._matched_base_ids(char_bases, q) if q else None
        prefixes = {str(cid) for cid in matched_ids} if matched_ids is not None else None
        only_anim = options.animated_only or (animated_cids is not None)

        selected: list[dict] = []
        for c in cards:
            cid_str = str(c.get("id", ""))
            if target_rar and c.get("rarity") != target_rar:
                continue
            if only_anim:
                if animated_cids:
                    if cid_str not in animated_cids:
                        continue
                elif (c.get("rarity") or 0) < 4:
                    continue
            if q:
                actor_hit = f"{c.get('actor', '')} {c.get('actorRomanization', '')} {c.get('fullName', '')}".lower()
                # Card id encodes actor id inside positions [1..3] or prefix matches
                if q not in cid_str and q not in actor_hit and not (prefixes and any(pid in cid_str[:5] for pid in prefixes)):
                    continue
            selected.append(c)
        if options.limit:
            selected = selected[: options.limit]
        return selected

    def run_category(self, category: str, options: DownloadOptions) -> CategoryResult:
        cards, char_bases, base_by_id, posters, spines = self._load_masterdata(options)

        if category == "live2d":
            return self._download_spine(char_bases, base_by_id, spines, options)
        if category == "card":
            return self._download_cards(cards, char_bases, options)
        if category == "card_animation":
            return self._download_card_animations(cards, char_bases, options)
        if category == "character":
            return self._download_characters(cards, char_bases, base_by_id, posters, options)

        return CategoryResult(game=self.code, category=category, supported=False, note=f"Unknown category: {category}")

    def _download_cards(self, cards: list[dict], char_bases: list[dict], options: DownloadOptions) -> CategoryResult:
        base_out = self.game_dir(options) / "card"
        anim_cids: set[str] | None = None
        if options.animated_only:
            ver = self._get_asset_version(options)
            groups = self._load_2dcatalog_groups(options, ver=ver)
            anim_cids = set(self._animated_card_bundles_by_cid(groups).keys())

        selected = self._filter_cards(cards, char_bases, options, animated_cids=anim_cids)
        tasks: list[DownloadTask] = []
        for c in selected:
            cid = str(c["id"])
            rar = c.get("rarity", 0)
            actor = sanitize_filename(c.get("actorRomanization") or c.get("actor") or cid)
            cdir = base_out / f"{cid}_r{rar}_{actor}"
            for variant in ("0.png", "cover0.png"):
                tasks.append(
                    DownloadTask(
                        url=f"{SIRIUS_RAW}/card/{cid}/{variant}",
                        dest=cdir / variant,
                        optional=(variant != "0.png"),
                    )
                )
            if rar >= 3:
                for variant in ("1.png", "cover1.png"):
                    tasks.append(
                        DownloadTask(
                            url=f"{SIRIUS_RAW}/card/{cid}/{variant}",
                            dest=cdir / variant,
                            optional=True,
                        )
                    )
            # Transparent cutout render hosted on Adv-Resource when available
            tasks.append(
                DownloadTask(
                    url=f"{ADV_RAW}/card/{cid}_0.png",
                    dest=cdir / f"cutout_{cid}_0.png",
                    optional=True,
                )
            )
            if rar >= 3:
                tasks.append(
                    DownloadTask(
                        url=f"{ADV_RAW}/card/{cid}_1.png",
                        dest=cdir / f"cutout_{cid}_1.png",
                        optional=True,
                    )
                )

        note = "Card 1920x1180 Full Illustration (normal/awake + cover) จาก sirius-decrypted-data + Adv-Resource"
        if options.animated_only:
            note += " (กรองเฉพาะการ์ดที่มีเวอร์ชัน Animation)"
        return run_download_tasks(
            tasks,
            game=self.code,
            category="card",
            output_path=base_out,
            threads=options.threads,
            note=note,
        )

    def _download_card_animations(
        self,
        cards: list[dict],
        char_bases: list[dict],
        options: DownloadOptions,
    ) -> CategoryResult:
        base_out = self.game_dir(options) / "card_animation"
        ver = self._get_asset_version(options)
        groups = self._load_2dcatalog_groups(options, ver=ver)
        anim_by_cid = self._animated_card_bundles_by_cid(groups)

        if not anim_by_cid:
            return CategoryResult(
                game=self.code,
                category="card_animation",
                supported=True,
                output_path=base_out,
                note="ไม่พบรายการ charactercards_assets_charactercard ใน Addressables catalog (ต้องใช้ brotli)",
            )

        selected = self._filter_cards(
            cards, char_bases, options, animated_cids=set(anim_by_cid.keys())
        )
        if not selected:
            return CategoryResult(
                game=self.code,
                category="card_animation",
                supported=True,
                output_path=base_out,
                note="ไม่พบการ์ดที่มี Animation ตามตัวกรอง (Yumesute มีเวอร์ชัน Animation เฉพาะ SSR 4★ ปลุกพลัง _1 และซีรีส์ 15xxxx)",
            )

        jobs: list[tuple[dict, str, str, Path]] = []
        res = CategoryResult(game=self.code, category="card_animation", supported=True, output_path=base_out)

        for c in selected:
            cid = str(c["id"])
            rar = c.get("rarity", 0)
            actor = sanitize_filename(c.get("actorRomanization") or c.get("actor") or cid)
            croot = base_out / f"{cid}_r{rar}_{actor}"
            for rel in anim_by_cid.get(cid, []):
                stem = Path(rel).stem
                dest_dir = croot / stem
                meta_ok = (dest_dir / "animation_meta.json").exists()
                tex_ok = (dest_dir / "textures").exists() and any((dest_dir / "textures").glob("*.png"))
                raw_ok = (not options.save_raw_bundle) or (dest_dir / f"{stem}.bundle").exists()
                if meta_ok and tex_ok and raw_ok:
                    res.total += 1
                    res.skipped += 1
                else:
                    jobs.append((c, rel, f"{CDN_2D}/{ver}/{rel}", dest_dir))

        if jobs:
            cdn_workers = max(1, min(options.threads, 2))
            print(
                f"[yumesute:card_animation] Downloading & extracting {len(jobs)} animated Actor Card bundles "
                f"(v{ver}, threads={cdn_workers})..."
            )

            def _fetch_one(url: str) -> bytes:
                time.sleep(0.35)
                return fetch_bytes(url, timeout=60, retries=4, reject_html=True)

            blobs: dict[str, bytes] = {}
            errors: dict[str, str] = {}
            with ThreadPoolExecutor(max_workers=cdn_workers) as pool:
                futs = {pool.submit(_fetch_one, url): (c, rel, url, dest_dir) for c, rel, url, dest_dir in jobs}
                for fut in as_completed(futs):
                    _, _, url, _ = futs[fut]
                    try:
                        blobs[url] = fut.result()
                    except Exception as exc:
                        errors[url] = str(exc)

            for c, rel, url, dest_dir in jobs:
                res.total += 1
                raw = blobs.get(url)
                if not raw:
                    res.failed += 1
                    if len(res.errors) < 10:
                        res.errors.append(f"{url}: {errors.get(url, 'Download failed')}")
                    continue
                stem = Path(rel).stem
                try:
                    extract_animated_card_bundle(
                        raw,
                        dest_dir,
                        fallback_version="2022.3.21f1",
                        extra_meta={
                            "game": self.code,
                            "card_id": c["id"],
                            "variant": stem,
                            "rarity": c.get("rarity"),
                            "actor": c.get("actor"),
                            "actor_romanization": c.get("actorRomanization"),
                            "title": c.get("fullName") or c.get("name"),
                            "asset_version": ver,
                            "source_url": url,
                        },
                        save_raw_bundle=options.save_raw_bundle,
                        bundle_filename=f"{stem}.bundle",
                    )
                    res.downloaded += 1
                except Exception as exc:
                    res.failed += 1
                    if len(res.errors) < 10:
                        res.errors.append(f"{stem}: {exc}")

        res.note = (
            f"Animated Actor Cards (v{ver}): แตกชั้น 1920x1180 + FX Sprite Sheets + Mask + Shader/Holo JSON"
            + (" + .bundle" if options.save_raw_bundle else "")
        )
        return res

    def _download_characters(
        self,
        cards: list[dict],
        char_bases: list[dict],
        base_by_id: dict[int, dict],
        posters: list[dict],
        options: DownloadOptions,
    ) -> CategoryResult:
        base_out = self.game_dir(options) / "character"
        q = (options.character or "").strip().lower()
        matched_ids = self._matched_base_ids(char_bases, q) if q else None
        selected_cards = self._filter_cards(cards, char_bases, options)

        target_rar = self._POSTER_RARITY_MAP.get((options.rarity or "").lower())
        selected_posters: list[dict] = []
        for p in posters:
            if target_rar and p.get("Rarity") != target_rar:
                continue
            if matched_ids is not None:
                appear = set(p.get("AppearanceCharacterBaseMasterIds") or [])
                if not appear.intersection(matched_ids) and q not in (p.get("Name", "") or "").lower():
                    continue
            selected_posters.append(p)
        if options.limit:
            selected_posters = selected_posters[: options.limit]

        tasks: list[DownloadTask] = []
        for c in selected_cards:
            cid = str(c["id"])
            rar = c.get("rarity", 0)
            tasks.append(
                DownloadTask(
                    url=f"{ADV_RAW}/image/cardIcon/{cid}_0.png",
                    dest=base_out / "card_icons" / f"{cid}_0.png",
                    optional=True,
                )
            )
            if rar >= 3:
                tasks.append(
                    DownloadTask(
                        url=f"{ADV_RAW}/image/cardIcon/{cid}_1.png",
                        dest=base_out / "card_icons" / f"{cid}_1.png",
                        optional=True,
                    )
                )
        for p in selected_posters:
            pid = p["Id"]
            pname = sanitize_filename(p.get("Name") or str(pid))
            tasks.append(
                DownloadTask(
                    url=f"{ADV_RAW}/image/posterIcon/{pid}.png",
                    dest=base_out / "poster_icons" / f"{pid}_{pname}.png",
                    optional=True,
                )
            )

        res = run_download_tasks(
            tasks,
            game=self.code,
            category="character",
            output_path=base_out,
            threads=options.threads,
        )

        # Optionally extract full-res Posters (1357x1920) & Character Signatures from live Unity CDN
        try:
            import UnityPy  # noqa: F401
            has_unity = True
        except ImportError:
            has_unity = False

        if has_unity:
            ver = self._get_asset_version(options)
            groups = self._load_2dcatalog_groups(options, ver=ver)
            bundle_jobs: list[tuple[str, Path, str]] = []

            poster_rels = {Path(r).stem: r for r in groups.get("posters_assets_posters", [])}
            for p in selected_posters:
                pid_s = str(p["Id"])
                rel = poster_rels.get(pid_s)
                if not rel:
                    continue
                pname = sanitize_filename(p.get("Name") or pid_s)
                dest_dir = base_out / "posters_full" / f"{pid_s}_{pname}"
                if dest_dir.exists() and any(dest_dir.glob("*.png")):
                    res.total += 1
                    res.skipped += 1
                else:
                    bundle_jobs.append((f"{CDN_2D}/{ver}/{rel}", dest_dir, f"poster_{pid_s}"))

            sign_rels = groups.get("charactersign_assets_charactersign", [])
            sign_filtered = []
            for rel in sign_rels:
                stem = Path(rel).stem
                if matched_ids is not None and not (stem.isdigit() and int(stem) in matched_ids):
                    continue
                sign_filtered.append((stem, rel))
            if options.limit:
                sign_filtered = sign_filtered[: options.limit]
            for stem, rel in sign_filtered:
                dest_dir = base_out / "signatures" / stem
                if dest_dir.exists() and any(dest_dir.glob("*.png")):
                    res.total += 1
                    res.skipped += 1
                else:
                    bundle_jobs.append((f"{CDN_2D}/{ver}/{rel}", dest_dir, f"sign_{stem}"))

            if bundle_jobs:
                cdn_workers = max(1, min(options.threads, 2))
                print(f"[yumesute:character] Extracting {len(bundle_jobs)} live CDN Unity bundles (v{ver})...")

                def _fetch_cdn(u: str) -> bytes:
                    time.sleep(0.35)
                    return fetch_bytes(u, timeout=60, retries=4, reject_html=True)

                blobs: dict[str, bytes] = {}
                with ThreadPoolExecutor(max_workers=cdn_workers) as pool:
                    futs = {pool.submit(_fetch_cdn, u): u for u, _, _ in bundle_jobs}
                    for fut in as_completed(futs):
                        u = futs[fut]
                        try:
                            blobs[u] = fut.result()
                        except Exception:
                            pass
                for u, dest_dir, _label in bundle_jobs:
                    res.total += 1
                    raw = blobs.get(u)
                    if not raw:
                        continue
                    try:
                        saved = extract_textures_and_texts(raw, dest_dir, fallback_version="2022.3.21f1")
                        if saved:
                            res.downloaded += 1
                    except Exception:
                        pass

        res.note = (
            "Character card/poster icons จาก Adv-Resource"
            + (" + Full Posters (1357x1920) & Signatures จาก live CDN" if has_unity else "")
        )
        return res

    def _download_spine(
        self,
        char_bases: list[dict],
        base_by_id: dict[int, dict],
        spines: list[dict],
        options: DownloadOptions,
    ) -> CategoryResult:
        # Yumesute uses Spine 4.1 rigs rather than Live2D Cubism
        base_out = self.game_dir(options) / "spine"
        q = (options.character or "").strip().lower()
        matched_ids = self._matched_base_ids(char_bases, q) if q else None

        filtered = []
        seen: set[int] = set()
        for sp in spines:
            sid = sp.get("Id")
            cid = sp.get("CharacterId")
            if not sid or sid in seen:
                continue
            if matched_ids is not None and cid not in matched_ids:
                continue
            seen.add(sid)
            filtered.append(sp)
        if options.limit:
            filtered = filtered[: options.limit]

        tasks: list[DownloadTask] = []
        for sp in filtered:
            sid = sp["Id"]
            cid = sp.get("CharacterId", 0)
            ch = base_by_id.get(cid, {})
            cname = sanitize_filename(ch.get("NameRomanization") or ch.get("Name") or str(cid))
            sdir = base_out / f"{sid}_{cid}_{cname}"
            for ext in ("skel", "atlas", "png"):
                tasks.append(
                    DownloadTask(
                        url=f"{ADV_RAW}/spine/{sid}.{ext}",
                        dest=sdir / f"{sid}.{ext}",
                        optional=(ext == "atlas"),
                    )
                )

        return run_download_tasks(
            tasks,
            game=self.code,
            category="live2d",
            output_path=base_out,
            threads=options.threads,
            note="Yumesute ใช้ Spine 4.1 (.skel + .atlas + .png) แทน Live2D — บันทึกลงโฟลเดอร์ spine/",
        )
