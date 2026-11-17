"""Adapter for THE IDOLM@STER Million Live! Theater Days (MLTD)."""

from __future__ import annotations

from core.base import (
    CategoryResult,
    DownloadOptions,
    DownloadTask,
    GameAdapter,
    sanitize_filename,
)
from core.http_client import load_or_fetch_json, run_download_tasks


class MLTDAdapter(GameAdapter):
    code = "mltd"
    name = "THE iDOLM@STER Million Live! Theater Days"
    credits = "Matsurihi Princess API & Storage (matsurihi.me)"
    supported_regions = ("jp",)

    _RARITY_MAP = {
        "n": {1},
        "r": {2},
        "sr": {3},
        "ssr": {4},
    }

    def _load_masterdata(self, options: DownloadOptions):
        mdir = self.masterdata_dir(options)
        cards = load_or_fetch_json(
            mdir / "cards.json",
            "https://api.matsurihi.me/api/mltd/v2/cards",
            refresh=options.refresh_masterdata,
        )
        idols = load_or_fetch_json(
            mdir / "idols.json",
            "https://api.matsurihi.me/api/mltd/v2/idols",
            refresh=options.refresh_masterdata,
        )
        idol_by_id = {i["id"]: i for i in idols if "id" in i}
        return cards, idol_by_id

    def _filter_cards(self, cards: list[dict], idol_by_id: dict[int, dict], options: DownloadOptions) -> list[dict]:
        allowed_rar = self._RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()
        selected: list[dict] = []
        for c in cards:
            rar = c.get("rarity")
            if allowed_rar and rar not in allowed_rar:
                continue
            if q:
                iid = c.get("idolId")
                idol = idol_by_id.get(iid, {})
                haystack = " ".join(
                    str(x)
                    for x in (
                        iid,
                        c.get("name", ""),
                        idol.get("fullName", ""),
                        idol.get("fullNameRuby", ""),
                        idol.get("displayName", ""),
                        idol.get("alphabetName", ""),
                    )
                ).lower()
                if q not in haystack and str(iid) != q:
                    continue
            selected.append(c)
        if options.limit:
            selected = selected[: options.limit]
        return selected

    def run_category(self, category: str, options: DownloadOptions) -> CategoryResult:
        if category == "live2d":
            return CategoryResult(
                game=self.code,
                category=category,
                supported=False,
                note="MLTD ใช้โมเดล 3D ในเกม ไม่มีไฟล์ Live2D สาธารณะ",
            )

        cards, idol_by_id = self._load_masterdata(options)
        selected = self._filter_cards(cards, idol_by_id, options)
        base_out = self.game_dir(options) / category
        tasks: list[DownloadTask] = []

        if category == "card":
            for c in selected:
                cid = c["id"]
                res = c["resourceId"]
                rar = c.get("rarity", 0)
                for awake in (0, 1):
                    stage = "awake" if awake == 1 else "normal"
                    tasks.append(
                        DownloadTask(
                            url=f"https://storage.matsurihi.me/mltd/card/{res}_{awake}_a.png",
                            dest=base_out / f"{cid}_{res}_{stage}_framed.png",
                            optional=True,
                        )
                    )
                    tasks.append(
                        DownloadTask(
                            url=f"https://storage.matsurihi.me/mltd/card/{res}_{awake}_b.png",
                            dest=base_out / f"{cid}_{res}_{stage}_clean.png",
                            optional=True,
                        )
                    )
                    if rar >= 3:
                        tasks.append(
                            DownloadTask(
                                url=f"https://storage.matsurihi.me/mltd/card_bg_hq/{res}_{awake}.png",
                                dest=base_out / f"{cid}_{res}_{stage}_bg_hq.png",
                                optional=True,
                            )
                        )
        elif category == "character":
            for c in selected:
                cid = c["id"]
                res = c["resourceId"]
                iid = c.get("idolId", 0)
                idol = idol_by_id.get(iid, {})
                idol_slug = sanitize_filename(idol.get("alphabetName") or idol.get("fullName") or str(iid))
                for awake in (0, 1):
                    tasks.append(
                        DownloadTask(
                            url=f"https://storage.matsurihi.me/mltd/icon_l/{res}_{awake}.png",
                            dest=base_out / f"{iid}_{idol_slug}" / f"{cid}_{res}_a{awake}.png",
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
            cache_404_path=None if options.refresh_masterdata else (base_out.parent / f".{category}_404_urls.json"),
        )
