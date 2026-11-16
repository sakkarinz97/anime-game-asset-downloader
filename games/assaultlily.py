"""Adapter for Assault Lily: Last Bullet (ALLB)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from core.base import (
    CategoryResult,
    DownloadOptions,
    DownloadTask,
    GameAdapter,
    sanitize_filename,
)
from core.http_client import load_or_fetch_json, run_download_tasks

ARAYA_BASE = "https://raw.githubusercontent.com/LaTlcia/A.RA.YA/main/MasterdataBase"
ALLB_IMG = "https://allb.game-db.tw/images"
DESKPET_TREE_API = "https://api.github.com/repos/czk200518-hash/AssaultLily-deskpet/git/trees/main?recursive=1"
DESKPET_RAW = "https://raw.githubusercontent.com/czk200518-hash/AssaultLily-deskpet/main"


def allb_hash(value: str) -> str:
    """Truncated MD5 identifier `[8:24]` used by allb.game-db.tw asset URLs."""
    return hashlib.md5(value.encode("utf-8")).hexdigest()[8:24]


class AssaultLilyAdapter(GameAdapter):
    code = "assaultlily"
    name = "Assault Lily: Last Bullet"
    credits = "LaTlcia/A.RA.YA, allb.game-db.tw, & czk200518-hash/AssaultLily-deskpet"
    supported_regions = ("jp",)

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
        if category not in ("card", "character"):
            return CategoryResult(game=self.code, category=category, supported=False, note=f"Unknown category: {category}")

        cards, chars, jobs = self._load_masterdata(options)
        base_out = self.game_dir(options) / category
        tasks: list[DownloadTask] = []
        allowed_rar = self._RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()

        if category == "card":
            seen_keys: set[tuple[int, int]] = set()
            selected_cards: list[dict] = []
            for c in cards:
                uid = c.get("uniqueId")
                rar = c.get("rarity")
                if not uid or not rar:
                    continue
                if allowed_rar and rar not in allowed_rar:
                    continue
                if q:
                    hay = f"{uid} {c.get('name', '')} {c.get('sortName', '')}".lower()
                    if q not in hay:
                        continue
                key = (uid, rar)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                selected_cards.append(c)

            if options.limit:
                selected_cards = selected_cards[: options.limit]

            for c in selected_cards:
                uid = c["uniqueId"]
                rar = c["rarity"]
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

            return run_download_tasks(
                tasks,
                game=self.code,
                category="card",
                output_path=base_out,
                threads=options.threads,
                note=(
                    "Memoria จาก allb.game-db.tw (256x256 PNG; "
                    "หมวด character มีภาพ Costume Full Illus 1536x1174 + Standing @2x 900x1550)"
                ),
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
