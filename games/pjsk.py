"""Adapter for Project SEKAI COLORFUL STAGE! feat. Hatsune Miku (PJSK)."""

from __future__ import annotations

from urllib.parse import quote

from core.base import (
    CategoryResult,
    DownloadOptions,
    DownloadTask,
    GameAdapter,
    sanitize_filename,
)
from core.http_client import fetch_json, load_or_fetch_json, run_download_tasks


class PJSKAdapter(GameAdapter):
    code = "pjsk"
    name = "Project SEKAI COLORFUL STAGE! feat. Hatsune Miku"
    credits = "Moesekai (pjsk.moe / storage.pjsk.moe) & Sekai-World (sekai-master-db-diff)"
    supported_regions = ("jp", "en", "tw", "kr", "cn")

    _REGION_META = {
        "jp": ("Sekai-World/sekai-master-db-diff", "jp"),
        "en": ("Sekai-World/sekai-master-db-en-diff", "en"),
        "tw": ("Sekai-World/sekai-master-db-tc-diff", "tc"),
        "kr": ("Sekai-World/sekai-master-db-kr-diff", "kr"),
        "cn": ("Sekai-World/sekai-master-db-cn-diff", "cn"),
    }

    _RARITY_MAP = {
        "1": {"rarity_1"},
        "r": {"rarity_1", "rarity_2"},
        "2": {"rarity_2"},
        "3": {"rarity_3"},
        "sr": {"rarity_3"},
        "4": {"rarity_4"},
        "ssr": {"rarity_4"},
        "bd": {"rarity_birthday"},
        "birthday": {"rarity_birthday"},
    }

    _LIVE2D_HEADERS = {"Referer": "https://pjsk.moe/"}

    def _region_cfg(self, region: str) -> tuple[str, str]:
        return self._REGION_META.get(region.lower(), self._REGION_META["jp"])

    def _load_masterdata(self, options: DownloadOptions):
        repo, _ = self._region_cfg(options.region)
        mdir = self.masterdata_dir(options)
        cards = load_or_fetch_json(
            mdir / f"cards_{options.region}.json",
            f"https://raw.githubusercontent.com/{repo}/main/cards.json",
            refresh=options.refresh_masterdata,
        )
        chars = load_or_fetch_json(
            mdir / f"gameCharacters_{options.region}.json",
            f"https://raw.githubusercontent.com/{repo}/main/gameCharacters.json",
            refresh=options.refresh_masterdata,
        )
        char_by_id = {c["id"]: c for c in chars if "id" in c}
        return cards, char_by_id

    def _matching_char_ids(self, char_by_id: dict[int, dict], query: str) -> set[int]:
        q = query.strip().lower()
        out = set()
        for cid, ch in char_by_id.items():
            haystack = " ".join(
                str(x)
                for x in (
                    cid,
                    ch.get("firstName", ""),
                    ch.get("givenName", ""),
                    ch.get("firstNameRuby", ""),
                    ch.get("givenNameRuby", ""),
                    ch.get("unit", ""),
                )
            ).lower()
            if q in haystack or str(cid) == q:
                out.add(cid)
        return out

    def _filter_cards(self, cards: list[dict], char_by_id: dict[int, dict], options: DownloadOptions) -> list[dict]:
        allowed_rar = self._RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()
        char_ids = self._matching_char_ids(char_by_id, q) if q else None

        selected: list[dict] = []
        for c in cards:
            if allowed_rar and c.get("cardRarityType") not in allowed_rar:
                continue
            if q:
                cid = c.get("characterId")
                if cid not in char_ids and q not in (c.get("prefix", "") or "").lower() and q not in c.get("assetbundleName", "").lower():
                    continue
            selected.append(c)
        if options.limit:
            selected = selected[: options.limit]
        return selected

    def run_category(self, category: str, options: DownloadOptions) -> CategoryResult:
        _, asset_region = self._region_cfg(options.region)
        cdn = f"https://storage.pjsk.moe/sekai-{asset_region}-assets"
        base_out = self.game_dir(options) / category

        if category == "live2d":
            return self._download_live2d(options, asset_region, base_out)

        cards, char_by_id = self._load_masterdata(options)
        selected = self._filter_cards(cards, char_by_id, options)
        tasks: list[DownloadTask] = []

        if category == "card":
            for c in selected:
                cid = c["id"]
                ab = c["assetbundleName"]
                has_trained = c.get("cardRarityType") in ("rarity_3", "rarity_4")
                tasks.append(
                    DownloadTask(
                        url=f"{cdn}/character/member/{ab}/card_normal.png",
                        dest=base_out / f"{cid}_{ab}" / "card_normal.png",
                    )
                )
                if has_trained:
                    tasks.append(
                        DownloadTask(
                            url=f"{cdn}/character/member/{ab}/card_after_training.png",
                            dest=base_out / f"{cid}_{ab}" / "card_after_training.png",
                            optional=True,
                        )
                    )
        elif category == "character":
            seen_chars: set[int] = set()
            for c in selected:
                cid = c["id"]
                ab = c["assetbundleName"]
                has_trained = c.get("cardRarityType") in ("rarity_3", "rarity_4")
                tasks.append(
                    DownloadTask(
                        url=f"{cdn}/character/member_cutout_trm/{ab}/normal.png",
                        dest=base_out / "cutout_trm" / f"{cid}_{ab}_normal.png",
                        optional=True,
                    )
                )
                tasks.append(
                    DownloadTask(
                        url=f"{cdn}/character/member_cutout/{ab}/normal.png",
                        dest=base_out / "cutout" / f"{cid}_{ab}_normal.png",
                        optional=True,
                    )
                )
                if has_trained:
                    tasks.append(
                        DownloadTask(
                            url=f"{cdn}/character/member_cutout_trm/{ab}/after_training.png",
                            dest=base_out / "cutout_trm" / f"{cid}_{ab}_after_training.png",
                            optional=True,
                        )
                    )
                    tasks.append(
                        DownloadTask(
                            url=f"{cdn}/character/member_cutout/{ab}/after_training.png",
                            dest=base_out / "cutout" / f"{cid}_{ab}_after_training.png",
                            optional=True,
                        )
                    )
                chid = c.get("characterId")
                if chid and chid not in seen_chars:
                    seen_chars.add(chid)
                    ch = char_by_id.get(chid, {})
                    cname = sanitize_filename(f"{ch.get('firstName', '')}{ch.get('givenName', '')}" or str(chid))
                    tasks.append(
                        DownloadTask(
                            url=f"https://moe.exmeaning.com/assets/chr_ts_{chid}.png",
                            dest=base_out / "icons" / f"chr_ts_{chid}_{cname}.png",
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

    def _download_live2d(self, options: DownloadOptions, asset_region: str, base_out) -> CategoryResult:
        mdir = self.masterdata_dir(options)
        raw_index = load_or_fetch_json(
            mdir / f"live2d_models_{asset_region}.json",
            f"https://assets.pjsk.moe/sekai-extra-assets/sekai-live2d/{asset_region}/models.json",
            refresh=options.refresh_masterdata,
            headers=self._LIVE2D_HEADERS,
        )
        if isinstance(raw_index, dict):
            top_lib = raw_index.get("library") or f"https://assets.pjsk.moe/sekai-extra-assets/sekai-story/ripper/{asset_region}/"
            models = list(raw_index.get("models") or [])
        else:
            top_lib = f"https://assets.pjsk.moe/sekai-extra-assets/sekai-story/ripper/{asset_region}/"
            models = list(raw_index or [])

        q = (options.character or "").strip().lower()
        if q:
            _, char_by_id = self._load_masterdata(options)
            matched_ids = self._matching_char_ids(char_by_id, q)
            prefixes = tuple(f"{cid:02d}" for cid in matched_ids)
            models = [
                m
                for m in models
                if m.get("characterId") in matched_ids
                or q in m.get("bundle", "").lower()
                or (prefixes and m.get("bundle", "").split("/")[-1].startswith(prefixes))
            ]
        if options.limit:
            models = models[: options.limit]

        tasks: list[DownloadTask] = []
        seen_bundles: set[str] = set()
        for entry in models:
            lib = entry.get("library") or top_lib
            if not lib.endswith("/"):
                lib += "/"

            bundle_items: list[tuple[str, bool]] = []
            if entry.get("bundle"):
                bundle_items.append((entry["bundle"], False))
            motion_list = entry.get("motions")
            if isinstance(motion_list, list):
                for mp in motion_list:
                    if mp:
                        bundle_items.append((mp, True))
            elif entry.get("motion"):
                bundle_items.append((entry["motion"], True))

            for bundle_path, is_motion in bundle_items:
                if bundle_path in seen_bundles:
                    continue
                seen_bundles.add(bundle_path)
                ripper_url = f"{lib}library/{bundle_path}/_ripper.json"
                try:
                    manifest = fetch_json(ripper_url, headers=self._LIVE2D_HEADERS)
                except Exception:
                    continue
                for f in manifest.get("files", []):
                    rel = f.get("path")
                    if not rel:
                        continue
                    file_url = f"{lib}library/{bundle_path}/{quote(rel)}"
                    tasks.append(
                        DownloadTask(
                            url=file_url,
                            dest=base_out / bundle_path / rel,
                            headers=self._LIVE2D_HEADERS,
                            optional=is_motion,
                        )
                    )

        return run_download_tasks(
            tasks,
            game=self.code,
            category="live2d",
            output_path=base_out,
            threads=options.threads,
            note="Live2D Cubism 3/4 + motions จาก Moesekai (pjsk.moe)",
        )
