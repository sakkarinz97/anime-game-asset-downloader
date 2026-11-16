"""Adapter for THE IDOLM@STER Cinderella Girls: Starlight Stage (CGSS)."""

from __future__ import annotations

from core.base import (
    CategoryResult,
    DownloadOptions,
    DownloadTask,
    GameAdapter,
    sanitize_filename,
)
from core.http_client import load_or_fetch_json, run_download_tasks


class CGSSAdapter(GameAdapter):
    code = "cgss"
    name = "THE iDOLM@STER Cinderella Girls: Starlight Stage"
    credits = "Starlight DB (starlight.kirara.ca / hidamarirhodonite.kirara.ca)"
    supported_regions = ("jp",)

    _RARITY_MAP = {
        "n": {1, 2},
        "r": {3, 4},
        "sr": {5, 6},
        "ssr": {7, 8},
    }

    def _load_masterdata(self, options: DownloadOptions):
        mdir = self.masterdata_dir(options)
        cards = load_or_fetch_json(
            mdir / "cards.json",
            "https://starlight.kirara.ca/api/v1/list/card_t",
            refresh=options.refresh_masterdata,
            transform=lambda d: d["result"] if isinstance(d, dict) and "result" in d else d,
        )
        chars = load_or_fetch_json(
            mdir / "characters.json",
            "https://starlight.kirara.ca/api/v1/list/char_t",
            refresh=options.refresh_masterdata,
            transform=lambda d: d["result"] if isinstance(d, dict) and "result" in d else d,
        )
        char_by_id = {c["chara_id"]: c for c in chars if "chara_id" in c}
        return cards, char_by_id

    def _filter_cards(self, cards: list[dict], char_by_id: dict[int, dict], options: DownloadOptions) -> list[dict]:
        allowed_rar = self._RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()
        selected: list[dict] = []
        for c in cards:
            rar = c.get("rarity_dep", {}).get("rarity")
            if allowed_rar and rar not in allowed_rar:
                continue
            if q:
                cid = c.get("chara_id")
                ch = char_by_id.get(cid, {})
                haystack = " ".join(
                    str(x)
                    for x in (
                        cid,
                        c.get("name_only", ""),
                        ch.get("name", ""),
                        ch.get("name_kana", ""),
                        ch.get("conventional", ""),
                        ch.get("kanji_spaced", ""),
                    )
                ).lower()
                if q not in haystack and str(cid) != q:
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
                note="CGSS ใช้โมเดล 3D และ 2D Puchi Sprite ในเกม ไม่มีไฟล์ Live2D สาธารณะ",
            )

        cards, char_by_id = self._load_masterdata(options)
        selected = self._filter_cards(cards, char_by_id, options)
        base_out = self.game_dir(options) / category
        tasks: list[DownloadTask] = []

        if category == "card":
            for c in selected:
                cid = c["id"]
                rar = c.get("rarity_dep", {}).get("rarity", 0)
                slug = sanitize_filename(c.get("name_only", str(cid)))
                tasks.append(
                    DownloadTask(
                        url=f"https://hidamarirhodonite.kirara.ca/card/{cid}.png",
                        dest=base_out / f"{cid}_{slug}_r{rar}_card.png",
                    )
                )
                if c.get("has_spread"):
                    tasks.append(
                        DownloadTask(
                            url=f"https://hidamarirhodonite.kirara.ca/spread/{cid}.png",
                            dest=base_out / f"{cid}_{slug}_r{rar}_spread.png",
                            optional=True,
                        )
                    )
        elif category == "character":
            for c in selected:
                cid = c["id"]
                chara_id = c.get("chara_id", 0)
                ch = char_by_id.get(chara_id, {})
                ch_slug = sanitize_filename(ch.get("conventional") or ch.get("name") or str(chara_id))
                tasks.append(
                    DownloadTask(
                        url=f"https://hidamarirhodonite.kirara.ca/icon_card/{cid}.png",
                        dest=base_out / "icon_card" / f"{cid}_{chara_id}_{ch_slug}.png",
                    )
                )
                tasks.append(
                    DownloadTask(
                        url=f"https://hidamarirhodonite.kirara.ca/puchi/{cid}.png",
                        dest=base_out / "puchi" / f"{cid}_{chara_id}_{ch_slug}.png",
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
