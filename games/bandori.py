"""Adapter for BanG Dream! Girls Band Party! (Bandori) via Bestdori API."""

from __future__ import annotations

import json
from pathlib import Path

from core.base import (
    CategoryResult,
    DownloadOptions,
    DownloadTask,
    GameAdapter,
    sanitize_filename,
)
from core.http_client import fetch_json, load_or_fetch_json, run_download_tasks


class BandoriAdapter(GameAdapter):
    code = "bandori"
    name = "BanG Dream! Girls Band Party!"
    credits = "Bestdori! (bestdori.com) — Live2D structure inspired by A-kirami/bestdori-live2d-downloader"
    supported_regions = ("jp", "en", "tw", "cn", "kr")

    _SERVER_IDX = {"jp": 0, "en": 1, "tw": 2, "cn": 3, "kr": 4}
    _RARITY_MAP = {"n": {1}, "1": {1}, "r": {2}, "2": {2}, "sr": {3}, "3": {3}, "ssr": {4}, "4": {4}, "5": {5}}

    def _region_idx(self, region: str) -> int:
        return self._SERVER_IDX.get(region.lower(), 0)

    def _pick_localized(self, arr, idx: int) -> str:
        if isinstance(arr, list):
            if idx < len(arr) and arr[idx]:
                return str(arr[idx])
            for item in arr:
                if item:
                    return str(item)
        return str(arr or "")

    def _load_masterdata(self, options: DownloadOptions):
        mdir = self.masterdata_dir(options)
        cards = load_or_fetch_json(
            mdir / "cards.json",
            "https://bestdori.com/api/cards/all.5.json",
            refresh=options.refresh_masterdata,
        )
        chars = load_or_fetch_json(
            mdir / "characters.json",
            "https://bestdori.com/api/characters/all.2.json",
            refresh=options.refresh_masterdata,
        )
        costumes = load_or_fetch_json(
            mdir / "costumes.json",
            "https://bestdori.com/api/costumes/all.5.json",
            refresh=options.refresh_masterdata,
        )
        return cards, chars, costumes

    def _matched_char_ids(self, chars: dict, query: str) -> set[int]:
        q = query.strip().lower()
        matched = set()
        for cid_s, ch in chars.items():
            name_all = " ".join(str(x) for x in (ch.get("characterName") or []) if x).lower()
            if cid_s == q or q in name_all:
                matched.add(int(cid_s))
        return matched

    def _filter_cards(self, cards: dict, chars: dict, options: DownloadOptions) -> list[tuple[str, dict]]:
        allowed_rar = self._RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()
        char_ids = self._matched_char_ids(chars, q) if q else None
        idx = self._region_idx(options.region)

        items = []
        for cid_s, c in sorted(cards.items(), key=lambda kv: int(kv[0])):
            if allowed_rar and c.get("rarity") not in allowed_rar:
                continue
            if char_ids is not None and c.get("characterId") not in char_ids:
                prefix = self._pick_localized(c.get("prefix"), idx).lower()
                if q not in prefix:
                    continue
            if not c.get("resourceSetName"):
                continue
            items.append((cid_s, c))
        if options.limit:
            items = items[: options.limit]
        return items

    def run_category(self, category: str, options: DownloadOptions) -> CategoryResult:
        region = options.region.lower()
        if region not in self._SERVER_IDX:
            region = "jp"
        idx = self._region_idx(region)
        cards, chars, costumes = self._load_masterdata(options)
        base_out = self.game_dir(options) / category

        if category == "live2d":
            return self._download_live2d(region, idx, chars, costumes, options, base_out)

        selected_cards = self._filter_cards(cards, chars, options)
        tasks: list[DownloadTask] = []

        if category == "card":
            for cid_s, c in selected_cards:
                res = c["resourceSetName"]
                rar = c.get("rarity", 0)
                base_url = f"https://bestdori.com/assets/{region}/characters/resourceset/{res}_rip"
                tasks.append(
                    DownloadTask(
                        url=f"{base_url}/card_normal.png",
                        dest=base_out / f"{cid_s}_{res}_r{rar}_normal.png",
                        optional=True,
                    )
                )
                if rar >= 3:
                    tasks.append(
                        DownloadTask(
                            url=f"{base_url}/card_after_training.png",
                            dest=base_out / f"{cid_s}_{res}_r{rar}_after_training.png",
                            optional=True,
                        )
                    )
        elif category == "character":
            seen_chars: set[int] = set()
            for cid_s, c in selected_cards:
                res = c["resourceSetName"]
                chid = c.get("characterId", 0)
                rar = c.get("rarity", 0)
                cname = sanitize_filename(self._pick_localized(chars.get(str(chid), {}).get("characterName"), idx) or str(chid))
                base_url = f"https://bestdori.com/assets/{region}/characters/resourceset/{res}_rip"
                tasks.append(
                    DownloadTask(
                        url=f"{base_url}/trim_normal.png",
                        dest=base_out / "trim" / f"{cid_s}_{res}_{cname}_trim_normal.png",
                        optional=True,
                    )
                )
                if rar >= 3:
                    tasks.append(
                        DownloadTask(
                            url=f"{base_url}/trim_after_training.png",
                            dest=base_out / "trim" / f"{cid_s}_{res}_{cname}_trim_after_training.png",
                            optional=True,
                        )
                    )
                if chid and chid not in seen_chars:
                    seen_chars.add(chid)
                    tasks.append(
                        DownloadTask(
                            url=f"https://bestdori.com/res/icon/chara_icon_{chid}.png",
                            dest=base_out / "icons" / f"chara_icon_{chid}_{cname}.png",
                            optional=True,
                        )
                    )

            # Live SD chibi sprites from costume details (/api/costumes/{id}.json)
            q = (options.character or "").strip().lower()
            char_ids = self._matched_char_ids(chars, q) if q else None
            cand_costumes = []
            for cos_id, cos in sorted(costumes.items(), key=lambda kv: int(kv[0])):
                if char_ids is not None and cos.get("characterId") not in char_ids:
                    continue
                cand_costumes.append((cos_id, cos))
                if options.limit and len(cand_costumes) >= options.limit:
                    break

            seen_sd: set[str] = set()
            for cos_id, _cos in cand_costumes:
                try:
                    detail = fetch_json(f"https://bestdori.com/api/costumes/{cos_id}.json")
                    sd = detail.get("sdResourceName")
                except Exception:
                    sd = None
                if not sd or sd in seen_sd:
                    continue
                seen_sd.add(sd)
                tasks.append(
                    DownloadTask(
                        url=f"https://bestdori.com/assets/{region}/characters/livesd/{sd}_rip/sdchara.png",
                        dest=base_out / "livesd" / f"{sd}.png",
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

    def _download_live2d(
        self,
        region: str,
        idx: int,
        chars: dict,
        costumes: dict,
        options: DownloadOptions,
        base_out: Path,
    ) -> CategoryResult:
        q = (options.character or "").strip().lower()
        char_ids = self._matched_char_ids(chars, q) if q else None

        models: list[tuple[str, dict]] = []
        seen_l2d: set[str] = set()
        for _, cos in sorted(costumes.items(), key=lambda kv: int(kv[0])):
            l2d = cos.get("assetBundleName") or cos.get("live2dAssetBundleName")
            if not l2d or l2d in seen_l2d:
                continue
            if char_ids is not None and cos.get("characterId") not in char_ids:
                if q not in l2d.lower():
                    continue
            seen_l2d.add(l2d)
            models.append((l2d, cos))
        if options.limit:
            models = models[: options.limit]

        tasks: list[DownloadTask] = []
        pending_model_jsons: list[tuple[Path, dict]] = []
        assets_root = f"https://bestdori.com/assets/{region}"

        for l2d_name, _cos in models:
            bd_url = f"{assets_root}/live2d/chara/{l2d_name}_rip/buildData.asset"
            try:
                raw_bd = fetch_json(bd_url)
            except Exception:
                continue
            base = raw_bd.get("Base")
            if not isinstance(base, dict):
                continue

            model_dir = base_out / l2d_name
            data_dir = model_dir / "data"
            mjson = {
                "version": "Sample 1.0.0",
                "layout": {"center_x": 0, "center_y": 0, "width": 2},
                "hit_areas_custom": {
                    "head_x": [-0.25, 1],
                    "head_y": [0.25, 0.2],
                    "body_x": [-0.3, 0.2],
                    "body_y": [0.3, -1.9],
                },
                "model": "",
                "physics": "",
                "textures": [],
                "motions": {},
                "expressions": [],
            }

            mdl_info = base.get("model") or {}
            if mdl_info.get("bundleName") and mdl_info.get("fileName"):
                fname = mdl_info["fileName"].removesuffix(".bytes")
                tasks.append(
                    DownloadTask(
                        url=f"{assets_root}/{mdl_info['bundleName']}_rip/{fname}",
                        dest=data_dir / "model.moc",
                    )
                )
                mjson["model"] = "data/model.moc"

            phy_info = base.get("physics") or {}
            if phy_info.get("bundleName") and phy_info.get("fileName"):
                tasks.append(
                    DownloadTask(
                        url=f"{assets_root}/{phy_info['bundleName']}_rip/{phy_info['fileName']}",
                        dest=data_dir / "physics.json",
                        optional=True,
                    )
                )
                mjson["physics"] = "data/physics.json"

            for tex in base.get("textures") or []:
                bname, fname = tex.get("bundleName"), tex.get("fileName")
                if not bname or not fname:
                    continue
                if "." not in fname:
                    fname += ".png"
                tasks.append(
                    DownloadTask(
                        url=f"{assets_root}/{bname}_rip/{fname}",
                        dest=data_dir / "textures" / fname,
                    )
                )
                mjson["textures"].append(f"data/textures/{fname}")

            for mot in base.get("motions") or []:
                bname, fname = mot.get("bundleName"), mot.get("fileName")
                if not bname or not fname:
                    continue
                fname = fname.removesuffix(".bytes")
                tasks.append(
                    DownloadTask(
                        url=f"{assets_root}/{bname}_rip/{fname}",
                        dest=data_dir / "motions" / fname,
                        optional=True,
                    )
                )
                key = fname.split(".", 1)[0]
                mjson["motions"][key] = [{"file": f"data/motions/{fname}"}]

            for exp in base.get("expressions") or []:
                bname, fname = exp.get("bundleName"), exp.get("fileName")
                if not bname or not fname:
                    continue
                tasks.append(
                    DownloadTask(
                        url=f"{assets_root}/{bname}_rip/{fname}",
                        dest=data_dir / "expressions" / fname,
                        optional=True,
                    )
                )
                mjson["expressions"].append(
                    {"name": fname.split(".", 1)[0], "file": f"data/expressions/{fname}"}
                )

            pending_model_jsons.append((model_dir / "model.json", mjson))

        res = run_download_tasks(
            tasks,
            game=self.code,
            category="live2d",
            output_path=base_out,
            threads=options.threads,
            note="Live2D Cubism 2 (.moc + model.json + motions + expressions) จาก Bestdori!",
        )
        for mpath, mobj in pending_model_jsons:
            mpath.parent.mkdir(parents=True, exist_ok=True)
            mpath.write_text(json.dumps(mobj, ensure_ascii=False, indent=2), encoding="utf-8")
        return res
