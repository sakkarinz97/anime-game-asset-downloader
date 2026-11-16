"""Adapter for BanG Dream! Our Notes via Moenotes (bdon.moe)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.base import (
    CategoryResult,
    DownloadOptions,
    DownloadTask,
    GameAdapter,
    sanitize_filename,
)
from core.http_client import fetch_bytes, fetch_json, load_or_fetch_json, run_download_tasks


class OurNotesAdapter(GameAdapter):
    code = "ournotes"
    name = "BanG Dream! Our Notes"
    credits = "Moenotes (bdon.moe / assets.bdon.moe) & StarMoe-org/moenotes-masterdata"
    supported_regions = ("hk-tw-mo", "en", "jp")

    _REGION_MAP = {
        "hk-tw-mo": ("hk-tw-mo", "zh-Hans"),
        "tw": ("hk-tw-mo", "zh-Hans"),
        "en": ("en", "en"),
        "jp": ("jp", "jp/ja"),
    }

    _RARITY_MAP = {
        "r": {2},
        "2": {2},
        "sr": {3},
        "3": {3},
        "ssr": {4},
        "4": {4},
        "ex": {10},
        "bd": {20},
    }

    def _region_cfg(self, region: str) -> tuple[str, str]:
        return self._REGION_MAP.get(region.lower(), self._REGION_MAP["hk-tw-mo"])

    @staticmethod
    def _unwrap_all_data(data: Any) -> list[dict]:
        if isinstance(data, dict) and isinstance(data.get("_allData"), list):
            return data["_allData"]
        return data if isinstance(data, list) else []

    def _load_masterdata(self, options: DownloadOptions):
        repo_region, _ = self._region_cfg(options.region)
        mdir = self.masterdata_dir(options)
        base = f"https://raw.githubusercontent.com/StarMoe-org/moenotes-masterdata/main/{repo_region}"
        member_cards = self._unwrap_all_data(
            load_or_fetch_json(
                mdir / f"MasterMemberCard_{repo_region}.json",
                f"{base}/MasterMemberCard.json",
                refresh=options.refresh_masterdata,
                transform=self._unwrap_all_data,
            )
        )
        support_cards = self._unwrap_all_data(
            load_or_fetch_json(
                mdir / f"MasterSupportCard_{repo_region}.json",
                f"{base}/MasterSupportCard.json",
                refresh=options.refresh_masterdata,
                transform=self._unwrap_all_data,
            )
        )
        chars = self._unwrap_all_data(
            load_or_fetch_json(
                mdir / f"MasterCharacter_{repo_region}.json",
                f"{base}/MasterCharacter.json",
                refresh=options.refresh_masterdata,
                transform=self._unwrap_all_data,
            )
        )
        char_by_id = {c["_id"]: c for c in chars if isinstance(c, dict) and "_id" in c}
        return member_cards, support_cards, chars, char_by_id

    def _matched_char_ids(self, chars: list[dict], query: str) -> set[int]:
        q = query.strip().lower()
        out = set()
        for ch in chars:
            cid = ch.get("_id")
            haystack = " ".join(
                str(x)
                for x in (
                    cid,
                    ch.get("_name", ""),
                    ch.get("_firstName", ""),
                    ch.get("_lastName", ""),
                    ch.get("_nameTextID", ""),
                    ch.get("_romaji", ""),
                )
            ).lower()
            if q in haystack or str(cid) == q:
                out.add(cid)
        return out

    def _list_asset_dir(self, lang_prefix: str, key_path: str) -> dict[str, str]:
        """Returns {filename: direct_url} from assets.bdon.moe listing JSON."""
        dir_url = f"https://assets.bdon.moe/{lang_prefix}/{key_path}/"
        try:
            listing = fetch_json(dir_url)
        except Exception:
            return {}
        files = listing.get("files") if isinstance(listing, dict) else None
        out: dict[str, str] = {}
        if isinstance(files, list):
            for f in files:
                name = f.get("name") or f.get("path") if isinstance(f, dict) else str(f)
                if name:
                    base_name = name.split("/")[-1]
                    out[base_name] = f"{dir_url}{base_name}"
        elif isinstance(files, dict):
            for name in files.keys():
                base_name = str(name).split("/")[-1]
                out[base_name] = f"{dir_url}{base_name}"
        return out

    def run_category(self, category: str, options: DownloadOptions) -> CategoryResult:
        _, lang_prefix = self._region_cfg(options.region)
        base_out = self.game_dir(options) / category

        if category == "live2d":
            return self._download_live2d(options, base_out)

        member_cards, support_cards, chars, char_by_id = self._load_masterdata(options)
        allowed_rar = self._RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()
        char_ids = self._matched_char_ids(chars, q) if q else None
        tasks: list[DownloadTask] = []

        if category == "card":
            m_filtered = [
                c
                for c in member_cards
                if (not allowed_rar or c.get("_rarity") in allowed_rar)
                and (
                    char_ids is None
                    or c.get("_characterID") in char_ids
                    or q in str(c.get("_nameTextID", "")).lower()
                )
            ]
            s_filtered = [
                c
                for c in support_cards
                if (not allowed_rar or c.get("_rarity") in allowed_rar)
                and (
                    char_ids is None
                    or any(cid in char_ids for cid in c.get("_characterIDs", []))
                    or q in str(c.get("_nameTextID", "")).lower()
                )
            ]
            if options.limit:
                m_filtered = m_filtered[: options.limit]
                s_filtered = s_filtered[: max(1, options.limit // 2)] if s_filtered else []

            for c in m_filtered:
                aid = c.get("_assetID") or c.get("_id")
                cid = c.get("_id")
                if not aid:
                    continue
                for subkey in ("member_full", "member_background"):
                    listing = self._list_asset_dir(lang_prefix, f"MemberCard/{aid}/{subkey}")
                    for fname, url in listing.items():
                        if fname.endswith(".png"):
                            tasks.append(
                                DownloadTask(
                                    url=url,
                                    dest=base_out / "member_cards" / f"{cid}_asset{aid}" / fname,
                                    optional=True,
                                )
                            )
                    if not listing:
                        tasks.append(
                            DownloadTask(
                                url=f"https://assets.bdon.moe/{lang_prefix}/MemberCard/{aid}/{subkey}/{subkey}.png",
                                dest=base_out / "member_cards" / f"{cid}_asset{aid}" / f"{subkey}.png",
                                optional=True,
                            )
                        )

            for sc in s_filtered:
                aid = sc.get("_assetID") or sc.get("_id")
                scid = sc.get("_id")
                if not aid:
                    continue
                listing = self._list_asset_dir(lang_prefix, f"SupportCard/{aid}/snap_full")
                if listing:
                    for fname, url in listing.items():
                        if fname.endswith(".png"):
                            tasks.append(
                                DownloadTask(
                                    url=url,
                                    dest=base_out / "support_cards" / f"{scid}_asset{aid}_{fname}",
                                    optional=True,
                                )
                            )
                else:
                    tasks.append(
                        DownloadTask(
                            url=f"https://assets.bdon.moe/{lang_prefix}/SupportCard/{aid}/snap_full/snap_full.png",
                            dest=base_out / "support_cards" / f"{scid}_asset{aid}_snap_full.png",
                            optional=True,
                        )
                    )

        elif category == "character":
            c_filtered = [
                ch
                for ch in chars
                if char_ids is None or ch.get("_id") in char_ids
            ]
            if options.limit:
                c_filtered = c_filtered[: options.limit]

            for ch in c_filtered:
                chid = ch["_id"]
                cname = sanitize_filename(str(ch.get("_nameTextID") or chid))
                for subkey in ("character_sprite", "character_thumbnail", "character_face_icon"):
                    tasks.append(
                        DownloadTask(
                            url=f"https://assets.bdon.moe/{lang_prefix}/Character/Image/{chid}/{subkey}/{subkey}.png",
                            dest=base_out / f"{chid}_{cname}" / f"{subkey}.png",
                            optional=True,
                        )
                    )

            m_filtered = [
                c
                for c in member_cards
                if (not allowed_rar or c.get("_rarity") in allowed_rar)
                and (char_ids is None or c.get("_characterID") in char_ids)
            ]
            if options.limit:
                m_filtered = m_filtered[: options.limit]
            for c in m_filtered:
                aid = c.get("_assetID") or c.get("_id")
                if not aid:
                    continue
                tasks.append(
                    DownloadTask(
                        url=f"https://assets.bdon.moe/{lang_prefix}/MemberCard/{aid}/member_character/member_character.png",
                        dest=base_out / "card_cutouts" / f"{c['_id']}_asset{aid}_member_character.png",
                        optional=True,
                    )
                )
        else:
            return CategoryResult(game=self.code, category=category, supported=False, note=f"Unknown category: {category}")

        return run_download_tasks(
            tasks,
            game=self.code,
            category=category,
            output_path=base_out,
            threads=options.threads,
        )

    def _download_live2d(self, options: DownloadOptions, base_out: Path) -> CategoryResult:
        mdir = self.masterdata_dir(options)
        index = load_or_fetch_json(
            mdir / "live2d_models.json",
            "https://assets.bdon.moe/chart-site/models.json",
            refresh=options.refresh_masterdata,
        )
        models = index if isinstance(index, list) else index.get("models", [])
        q = (options.character or "").strip().lower()
        if q:
            _, _, chars, _ = self._load_masterdata(options)
            matched_ids = self._matched_char_ids(chars, q)
            tokens = {f"_{cid:03d}_" for cid in matched_ids}
            models = [
                m
                for m in models
                if q in m.get("id", "").lower()
                or m.get("character") in matched_ids
                or any(tok in m.get("id", "") for tok in tokens)
            ]
        if options.limit:
            models = models[: options.limit]

        tasks: list[DownloadTask] = []
        assembled_parts: list[tuple[Path, list[Any]]] = []
        site_root = "https://assets.bdon.moe/chart-site"

        for entry in models:
            mid = entry.get("id")
            if not mid:
                continue
            try:
                manifest = fetch_json(f"{site_root}/models/{mid}.json")
            except Exception:
                continue
            model_dir = base_out / mid
            for rel_path, spec in (manifest.get("files") or {}).items():
                if not isinstance(spec, dict):
                    continue
                if "asset" in spec:
                    tasks.append(
                        DownloadTask(
                            url=f"{site_root}/{spec['asset']}",
                            dest=model_dir / rel_path,
                        )
                    )
                elif "parts" in spec and isinstance(spec["parts"], list):
                    assembled_parts.append((model_dir / rel_path, spec["parts"]))

        res = run_download_tasks(
            tasks,
            game=self.code,
            category="live2d",
            output_path=base_out,
            threads=options.threads,
            note="Live2D Cubism 3/4 จาก Moenotes (bdon.moe)",
        )

        # Assemble chunked JSON files such as *.prefab.json
        for dest_path, parts in assembled_parts:
            if dest_path.exists() and dest_path.stat().st_size > 0:
                continue
            merged: dict[str, Any] = {}
            ok = True
            for part in parts:
                if not isinstance(part, list) or len(part) < 2:
                    continue
                pkey, passet = part[0], part[1]
                try:
                    raw = fetch_bytes(f"{site_root}/{passet}", reject_html=True)
                    merged[pkey] = json.loads(raw.decode("utf-8"))
                except Exception:
                    ok = False
            if merged:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
                res.total += 1
                res.downloaded += 1 if ok else 0
                if not ok:
                    res.failed += 1

        return res
