"""Adapter for Assault Lily: Last Bullet (ALLB)."""

from __future__ import annotations

import hashlib
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
from core.unity_utils import extract_animated_card_bundle

ARAYA_BASE = "https://raw.githubusercontent.com/LaTlcia/A.RA.YA/main/MasterdataBase"
ALLB_IMG = "https://allb.game-db.tw/images"
ALLB_CDN = "https://allb.tqlwsl.moe"
DESKPET_TREE_API = "https://api.github.com/repos/czk200518-hash/AssaultLily-deskpet/git/trees/main?recursive=1"
DESKPET_RAW = "https://raw.githubusercontent.com/czk200518-hash/AssaultLily-deskpet/main"


def allb_hash(value: str) -> str:
    """Truncated MD5 identifier `[8:24]` used by allb.game-db.tw asset URLs."""
    return hashlib.md5(value.encode("utf-8")).hexdigest()[8:24]


class AssaultLilyAdapter(GameAdapter):
    code = "assaultlily"
    name = "Assault Lily: Last Bullet"
    credits = "LaTlcia/A.RA.YA, allb.tqlwsl.moe, allb.game-db.tw & czk200518-hash/AssaultLily-deskpet"
    supported_regions = ("jp",)
    supports_card_animation = True

    _RARITY_MAP = {
        "r": {3},
        "3": {3},
        "sr": {4},
        "4": {4},
        "ssr": {5},
        "5": {5},
        "ur": {6},
        "6": {6},
        "lg": {7},
        "7": {7},
        "8": {8},
        "9": {9},
        "10": {10},
    }

    @staticmethod
    def _unwrap_mst(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict) and isinstance(data.get("payload"), dict):
            return data["payload"].get("mstList", []) or []
        return data if isinstance(data, list) else []

    @classmethod
    def _extract_card_prefabs(cls, data: Any) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in cls._unwrap_mst(data):
            ab = row.get("assetBundleName", "")
            if ab.startswith("asset_bundle/card_prefab/card_"):
                key = ab.split("asset_bundle/card_prefab/card_", 1)[-1]
                out[key] = {
                    "bundle": ab,
                    "windowsFileSize": row.get("windowsFileSize"),
                    "androidFileSize": row.get("androidFileSize"),
                }
        return out

    @classmethod
    def _extract_card_images(cls, data: Any) -> dict[str, str]:
        out: dict[str, str] = {}
        for row in cls._unwrap_mst(data):
            fn = row.get("fileName", "")
            if fn.startswith("Image/Card/") and fn.lower().endswith(".jpg"):
                stem = Path(fn).stem
                key = stem[4:] if stem.startswith("Card") else stem
                out[key] = fn
        return out

    def _load_masterdata(self, options: DownloadOptions):
        mdir = self.masterdata_dir(options)
        cards = load_or_fetch_json(
            mdir / "CardMstList.json",
            f"{ARAYA_BASE}/masterdata_api_mst_getCardMstList.json",
            refresh=options.refresh_masterdata,
            transform=self._unwrap_mst,
        )
        chars = load_or_fetch_json(
            mdir / "CharacterMstList.json",
            f"{ARAYA_BASE}/masterdata_api_mst_getCharacterMstList.json",
            refresh=options.refresh_masterdata,
            transform=self._unwrap_mst,
        )
        jobs = load_or_fetch_json(
            mdir / "CharacterJobMstList.json",
            f"{ARAYA_BASE}/masterdata_api_mst_getCharacterJobMstList.json",
            refresh=options.refresh_masterdata,
            transform=self._unwrap_mst,
        )
        return cards, chars, jobs

    def _load_card_resource_catalogs(self, options: DownloadOptions) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        mdir = self.masterdata_dir(options)
        prefab_map = load_or_fetch_json(
            mdir / "CardPrefabBundles.json",
            f"{ARAYA_BASE}/masterdata_api_mst_get_resource_asset_bundle_mst_list.json",
            refresh=options.refresh_masterdata,
            transform=self._extract_card_prefabs,
        )
        card_img_map = load_or_fetch_json(
            mdir / "CardImageFiles.json",
            f"{ARAYA_BASE}/masterdata_api_mst_get_resource_file_mst_list.json",
            refresh=options.refresh_masterdata,
            transform=self._extract_card_images,
        )
        return prefab_map, card_img_map

    @staticmethod
    def _matched_char_ids(chars: list[dict], query: str) -> set[int]:
        q = query.strip().lower()
        out: set[int] = set()
        for ch in chars:
            cid = ch.get("characterMstId")
            haystack = " ".join(
                str(x)
                for x in (
                    cid,
                    ch.get("name", ""),
                    ch.get("kanaName", ""),
                    ch.get("firstName", ""),
                    ch.get("cv", ""),
                )
            ).lower()
            if q in haystack or str(cid) == q:
                out.add(cid)
        return out

    def run_category(self, category: str, options: DownloadOptions) -> CategoryResult:
        if category == "live2d":
            return self._download_spine_samples(options)
        if category not in ("card", "card_animation", "character"):
            return CategoryResult(game=self.code, category=category, supported=False, note=f"Unknown category: {category}")

        cards, chars, jobs = self._load_masterdata(options)
        if category == "card_animation":
            return self._download_card_animations(cards, options)

        base_out = self.game_dir(options) / category
        tasks: list[DownloadTask] = []
        allowed_rar = self._RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()

        if category == "card":
            prefab_map, card_img_map = self._load_card_resource_catalogs(options)
            seen_keys: set[tuple[int, int]] = set()
            selected_cards: list[dict] = []
            for c in cards:
                uid = c.get("uniqueId")
                rar = c.get("rarity")
                if not uid or not rar:
                    continue
                if allowed_rar and rar not in allowed_rar:
                    continue
                uid_str = f"{int(uid):09d}"
                if options.animated_only and not (c.get("isAnimation") or uid_str in prefab_map):
                    continue
                if q:
                    hay = f"{uid} {uid_str} {c.get('name', '')} {c.get('sortName', '')}".lower()
                    if q not in hay:
                        continue
                key = (uid, rar)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                selected_cards.append(c)

            if options.limit:
                selected_cards = selected_cards[: options.limit]

            seen_full_uids: set[str] = set()
            for c in selected_cards:
                uid = c["uniqueId"]
                rar = c["rarity"]
                uid_str = f"{int(uid):09d}"
                h = allb_hash(f"{uid}_{rar}")
                slug = sanitize_filename(c.get("name") or str(uid))
                tasks.append(
                    DownloadTask(
                        url=f"{ALLB_IMG}/memoria/png/{h}.png",
                        dest=base_out / f"{uid}_r{rar}_{slug}.png",
                        optional=True,
                    )
                )
                if rar >= 6 or c.get("isInfinitelyEvolvable"):
                    tasks.append(
                        DownloadTask(
                            url=f"{ALLB_IMG}/memoria_ultimate/{h}.png",
                            dest=base_out / "ultimate" / f"{uid}_r{rar}_{slug}_ult.png",
                            optional=True,
                        )
                    )
                if uid_str in card_img_map and uid_str not in seen_full_uids:
                    seen_full_uids.add(uid_str)
                    tasks.append(
                        DownloadTask(
                            url=f"{ALLB_CDN}/{card_img_map[uid_str]}",
                            dest=base_out / "full" / f"{uid_str}_{slug}.jpg",
                            optional=True,
                        )
                    )

            note = "Memoria Full 800x600 JPG (allb.tqlwsl.moe/full) + 256x256 PNG (allb.game-db.tw)"
            if options.animated_only:
                note += " [กรองเฉพาะการ์ด Animated]"
            return run_download_tasks(
                tasks,
                game=self.code,
                category="card",
                output_path=base_out,
                threads=max(1, min(options.threads, 6)),
                note=note,
                request_delay=0.02,
                cache_404_path=None if options.refresh_masterdata else (base_out.parent / ".card_404_urls.json"),
            )

        # category == "character"
        char_ids = self._matched_char_ids(chars, q) if q else None
        filtered_chars = [ch for ch in chars if char_ids is None or ch.get("characterMstId") in char_ids]
        if options.limit:
            filtered_chars = filtered_chars[: options.limit]

        for ch in filtered_chars:
            cid = ch["characterMstId"]
            cname = sanitize_filename(ch.get("name") or str(cid))
            tasks.append(
                DownloadTask(
                    url=f"{ALLB_IMG}/chara/{cid}.png",
                    dest=base_out / "portraits" / f"{cid}_{cname}.png",
                    optional=True,
                )
            )

        filtered_jobs = [
            j
            for j in jobs
            if (char_ids is None or j.get("characterMstId") in char_ids or (q and q in str(j.get("name", "")).lower()))
        ]
        if options.limit:
            filtered_jobs = filtered_jobs[: options.limit]

        for j in filtered_jobs:
            jid = j["characterJobMstId"]
            jslug = sanitize_filename(j.get("name") or str(jid))
            h_body = allb_hash(f"cb{jid}")
            h_jpg = allb_hash(f"c{jid * jid}")
            h_png = allb_hash(f"c{jid}")
            tasks.append(
                DownloadTask(
                    url=f"{ALLB_IMG}/job/body/{h_body}%402x.png",
                    dest=base_out / "job_body_2x" / f"{jid}_{jslug}.png",
                    optional=True,
                )
            )
            tasks.append(
                DownloadTask(
                    url=f"{ALLB_IMG}/job/jpg/{h_jpg}.jpg",
                    dest=base_out / "job_illust" / f"{jid}_{jslug}.jpg",
                    optional=True,
                )
            )
            tasks.append(
                DownloadTask(
                    url=f"{ALLB_IMG}/job/png/{h_png}.png",
                    dest=base_out / "job_icon" / f"{jid}_{jslug}.png",
                    optional=True,
                )
            )

        return run_download_tasks(
            tasks,
            game=self.code,
            category="character",
            output_path=base_out,
            threads=options.threads,
            note="Character portraits + Costume Standing @2x (900x1550) + Full Illus (1536x1174 JPG) + Job Icon",
        )

    def _download_card_animations(self, cards: list[dict], options: DownloadOptions) -> CategoryResult:
        base_out = self.game_dir(options) / "card_animation"
        prefab_map, card_img_map = self._load_card_resource_catalogs(options)
        allowed_rar = self._RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()

        entries_by_key: dict[str, dict[str, Any]] = {}
        ordered_keys: list[str] = []

        # Map all variants sharing a base uniqueId (e.g., 010022015 and 010022015_01)
        keys_by_uid: dict[str, list[str]] = {}
        for pkey in sorted(prefab_map):
            base_uid = pkey.split("_", 1)[0]
            keys_by_uid.setdefault(base_uid, []).append(pkey)

        for c in cards:
            uid = c.get("uniqueId")
            rar = c.get("rarity")
            if not uid or not rar:
                continue
            if allowed_rar and rar not in allowed_rar:
                continue
            uid_str = f"{int(uid):09d}"
            matching_pkeys = keys_by_uid.get(uid_str, [])
            if not matching_pkeys:
                continue
            if q:
                hay = f"{uid} {uid_str} {c.get('name', '')} {c.get('sortName', '')}".lower()
                if q not in hay:
                    continue
            for pkey in matching_pkeys:
                if pkey not in entries_by_key:
                    entries_by_key[pkey] = {
                        "prefab_key": pkey,
                        "bundle": prefab_map[pkey]["bundle"],
                        "unique_id": uid,
                        "uid_str": uid_str,
                        "name": c.get("name") or pkey,
                        "rarities": [rar],
                        "card_mst_ids": [c.get("cardMstId")],
                        "is_animation": bool(c.get("isAnimation")),
                        "is_emoria": bool(c.get("isEmoria")),
                    }
                    ordered_keys.append(pkey)
                else:
                    info = entries_by_key[pkey]
                    if rar not in info["rarities"]:
                        info["rarities"].append(rar)
                    if c.get("cardMstId") not in info["card_mst_ids"]:
                        info["card_mst_ids"].append(c.get("cardMstId"))

        # Include catalog-only animated bundles (e.g., Emoria awakened forms card_090000000/090000001)
        if not allowed_rar:
            for pkey, binfo in sorted(prefab_map.items()):
                if pkey in entries_by_key:
                    continue
                if q and q not in pkey.lower():
                    continue
                entries_by_key[pkey] = {
                    "prefab_key": pkey,
                    "bundle": binfo["bundle"],
                    "unique_id": None,
                    "uid_str": pkey,
                    "name": f"card_{pkey}",
                    "rarities": [],
                    "card_mst_ids": [],
                    "is_animation": True,
                    "is_emoria": pkey.startswith(("08", "09")),
                }
                ordered_keys.append(pkey)

        if options.limit:
            ordered_keys = ordered_keys[: options.limit]

        res = CategoryResult(game=self.code, category="card_animation", supported=True, output_path=base_out)
        if not ordered_keys:
            res.note = "ไม่พบ Animated Memoria card_prefab ตามตัวกรองที่ระบุ"
            return res

        jobs: list[tuple[str, dict[str, Any], Path, str, str | None]] = []
        for pkey in ordered_keys:
            info = entries_by_key[pkey]
            rmin = min(info["rarities"]) if info["rarities"] else 0
            slug = sanitize_filename(info["name"])
            rtag = "emoria" if info["is_emoria"] else f"r{rmin}"
            dest_dir = base_out / f"{pkey}_{rtag}_{slug}"
            bundle_name = f"card_{pkey}.bundle"

            meta_ok = (dest_dir / "animation_meta.json").exists()
            tex_ok = (dest_dir / "textures").exists() and any((dest_dir / "textures").glob("*.png"))
            raw_ok = (not options.save_raw_bundle) or (dest_dir / bundle_name).exists()
            if meta_ok and tex_ok and raw_ok:
                res.total += 1
                res.skipped += 1
                continue

            ab_url = f"{ALLB_CDN}/{info['bundle']}"
            jpg_rel = card_img_map.get(info["uid_str"]) or card_img_map.get(pkey)
            jpg_url = f"{ALLB_CDN}/{jpg_rel}" if jpg_rel else None
            jobs.append((pkey, info, dest_dir, ab_url, jpg_url))

        if jobs:
            cdn_workers = max(1, min(options.threads, 4))
            print(
                f"[assaultlily:card_animation] Downloading & extracting {len(jobs)} animated Memoria bundles "
                f"from allb.tqlwsl.moe (threads={cdn_workers})..."
            )

            def _process_one(job: tuple) -> tuple[str, bool, str | None]:
                pkey, info, dest_dir, ab_url, jpg_url = job
                try:
                    time.sleep(0.15)
                    ab_raw = fetch_bytes(ab_url, timeout=90, retries=4, reject_html=True)
                    jpg_raw = None
                    if jpg_url:
                        try:
                            time.sleep(0.05)
                            jpg_raw = fetch_bytes(jpg_url, timeout=45, retries=3, reject_html=True)
                        except Exception:
                            jpg_raw = None

                    bundle_name = f"card_{pkey}.bundle"
                    extract_animated_card_bundle(
                        ab_raw,
                        dest_dir,
                        fallback_version="2022.3.21f1",
                        extra_meta={
                            "game": self.code,
                            "prefab_key": pkey,
                            "unique_id": info["unique_id"],
                            "name": info["name"],
                            "rarities": sorted(info["rarities"]),
                            "card_mst_ids": info["card_mst_ids"],
                            "is_animation": info["is_animation"],
                            "is_emoria": info["is_emoria"],
                            "source_bundle_url": ab_url,
                            "source_preview_url": jpg_url,
                        },
                        save_raw_bundle=options.save_raw_bundle,
                        bundle_filename=bundle_name,
                    )
                    if jpg_raw:
                        (dest_dir / "card_preview.jpg").write_bytes(jpg_raw)
                    return pkey, True, None
                except Exception as exc:
                    return pkey, False, str(exc)

            completed_count = 0
            with ThreadPoolExecutor(max_workers=cdn_workers) as pool:
                futs = {pool.submit(_process_one, job): job[0] for job in jobs}
                for fut in as_completed(futs):
                    completed_count += 1
                    res.total += 1
                    pkey, ok, err_msg = fut.result()
                    if ok:
                        res.downloaded += 1
                    else:
                        res.failed += 1
                        if len(res.errors) < 10:
                            res.errors.append(f"card_{pkey}: {err_msg}")
                    if completed_count % 25 == 0 or completed_count == len(jobs):
                        print(
                            f"[assaultlily:card_animation] Progress {completed_count}/{len(jobs)} "
                            f"(ok={res.downloaded}, skip={res.skipped}, fail={res.failed})"
                        )

        res.note = (
            "Animated Memoria Prefabs (allb.tqlwsl.moe): 2048x2048 Atlases + VFX Sprites + Emoria Spine 3.6 (.skel/.atlas/.png) + AnimationMeta JSON"
            + (" + .bundle" if options.save_raw_bundle else "")
        )
        return res

    def _download_spine_samples(self, options: DownloadOptions) -> CategoryResult:
        # Official CEDEC 2021 Pokelabo talk confirmed Assault Lily uses Spine rather than Live2D
        base_out = self.game_dir(options) / "spine"
        mdir = self.masterdata_dir(options)
        tree_data = load_or_fetch_json(
            mdir / "deskpet_tree.json",
            DESKPET_TREE_API,
            refresh=options.refresh_masterdata,
        )
        entries = tree_data.get("tree", []) if isinstance(tree_data, dict) else []

        # Group files by directory so --limit cleanly takes N Spine rig sets
        groups: dict[str, list[str]] = {}
        for item in entries:
            path = item.get("path", "")
            if not path.endswith((".skel", ".atlas", ".png")):
                continue
            fname = Path(path).name
            if not fname.startswith("CharacterJobSpine"):
                continue
            parent = Path(path).parent.name
            groups.setdefault(parent, []).append(path)

        selected_groups = sorted(groups.items())
        if options.limit:
            selected_groups = selected_groups[: options.limit]

        tasks: list[DownloadTask] = []
        for gname, paths in selected_groups:
            for rel in sorted(paths):
                tasks.append(
                    DownloadTask(
                        url=f"{DESKPET_RAW}/{rel}",
                        dest=base_out / gname / Path(rel).name,
                    )
                )

        return run_download_tasks(
            tasks,
            game=self.code,
            category="live2d",
            output_path=base_out,
            threads=options.threads,
            note=(
                "Assault Lily ใช้ Spine (อ้างอิง CEDEC 2021 ของ Pokelabo) ไม่มี Live2D — "
                "ดาวน์โหลดไฟล์ตัวอย่าง Spine (.skel + .atlas + .png) จาก community repo ลงโฟลเดอร์ spine/"
            ),
        )
