"""Adapter for Princess Connect! Re:Dive JP via esterTion / redive.estertion.win."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.base import (
    CategoryResult,
    DownloadOptions,
    DownloadTask,
    GameAdapter,
    sanitize_filename,
)
from core.http_client import fetch_bytes, run_download_tasks

REDIVE_BASE = "https://redive.estertion.win"

_SNAP_RX = re.compile(r"_\d{8}_\d{4}\.")
_HREF_RX = re.compile(r'<a href="([^"]+)">')
_NAMES_RX = re.compile(r"\bnames\s*=\s*(\{)")
_DETAILS_DS_RX = re.compile(r'<details[^>]*data-search="([^"]*)"')
_BOND_PREFIXES = {"10", "11", "12", "13", "14", "15", "16", "17", "18", "19"}


def _extract_names_map(html: str) -> dict[str, str]:
    m = _NAMES_RX.search(html)
    if not m:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, m.start(1))
        if isinstance(obj, dict):
            return {str(k): str(v) for k, v in obj.items() if v}
    except Exception:
        pass
    return {}


def _parse_listing(url_path: str, ext: str) -> tuple[list[str], dict[str, str]]:
    html = fetch_bytes(f"{REDIVE_BASE}{url_path}", timeout=45, retries=4).decode("utf-8", "replace")
    files = sorted(
        {
            href
            for href in _HREF_RX.findall(html)
            if href.endswith(ext) and not _SNAP_RX.search(href) and "/" not in href
        }
    )
    names = _extract_names_map(html)
    return files, names


def _parse_story_data_groups() -> tuple[list[dict[str, Any]], dict[str, str]]:
    html = fetch_bytes(f"{REDIVE_BASE}/story/data/", timeout=45, retries=4).decode("utf-8", "replace")
    groups: list[dict[str, Any]] = []
    unit_names: dict[str, str] = {}
    for blk in html.split("</details>"):
        m_ds = _DETAILS_DS_RX.search(blk)
        if not m_ds:
            continue
        ds = m_ds.group(1)
        parts = ds.split(",", 1)
        gid = parts[0].strip()
        gname = parts[1].strip() if len(parts) > 1 else ""
        files = sorted(
            {
                href
                for href in _HREF_RX.findall(blk)
                if href.endswith(".json") and not _SNAP_RX.search(href) and "/" not in href
            }
        )
        if not files:
            continue
        if gid[:2] in _BOND_PREFIXES and gname:
            unit_names[gid[:4]] = gname
        groups.append({"group_id": gid, "group_name": gname, "files": files})
    return groups, unit_names


def _story_bucket(gid: str) -> str:
    p2 = gid[:2]
    if p2 == "00":
        return "00_prologue_misc"
    if p2.startswith("2"):
        return "20_main_story"
    if p2.startswith("3"):
        return "30_guild_story"
    if p2.startswith("4"):
        return "40_system_birthday"
    if p2.startswith("5"):
        return "50_event_story"
    if p2.startswith("6"):
        return "60_extra_mini_story"
    if p2.startswith("7"):
        return "70_luna_tower"
    if p2.startswith("8"):
        return "80_short_cg"
    if p2.startswith("9"):
        return "90_anniversary_raid"
    return "other"


def _story_json_to_text(raw_json: str) -> str:
    cmds = json.loads(raw_json)
    if not isinstance(cmds, list):
        return raw_json

    title = ""
    outline = ""
    body_lines: list[str] = []
    pending_vo = ""
    cur_raw_speaker: str | None = None
    cur_label: str | None = None
    cur_buf: list[str] = []

    def flush_speaker() -> None:
        nonlocal cur_raw_speaker, cur_label, cur_buf
        if cur_label is not None and cur_buf:
            joined = "".join(cur_buf).strip()
            if joined:
                body_lines.append(f"[{cur_label}]")
                body_lines.append(joined)
                body_lines.append("")
        cur_raw_speaker = None
        cur_label = None
        cur_buf = []

    for cmd in cmds:
        if not isinstance(cmd, dict):
            continue
        name = cmd.get("name", "")
        args = cmd.get("args") or []
        if name == "title" and args:
            t = str(args[0]).strip()
            if t:
                title = t
        elif name == "outline" and args:
            o = str(args[0]).strip()
            if o:
                outline = o
        elif name == "situation" and args:
            flush_speaker()
            sit = str(args[0]).strip()
            if sit:
                body_lines.append(f"=== {sit} ===")
        elif name == "vo" and args:
            flush_speaker()
            pending_vo = str(args[0]).strip()
        elif name == "print" and len(args) >= 2:
            speaker = str(args[0]).strip() or "ナレーション"
            text = str(args[1])
            if cur_raw_speaker is not None and speaker != cur_raw_speaker:
                flush_speaker()
            if cur_raw_speaker is None:
                cur_raw_speaker = speaker
                cur_label = f"{speaker} ({pending_vo})" if pending_vo else speaker
                pending_vo = ""
            cur_buf.append(text)
        elif name == "touch":
            flush_speaker()
            pending_vo = ""
        elif name == "choice" and args:
            flush_speaker()
            label = str(args[0]).strip()
            tag_id = str(args[1]).strip() if len(args) > 1 else ""
            suffix = f" -> #{tag_id}" if tag_id else ""
            body_lines.append(f"  > [Choice{suffix}] {label}")
        elif name == "tag" and args:
            flush_speaker()
            body_lines.append(f"--- [Branch #{str(args[0]).strip()}] ---")
        elif name == "still" and args:
            flush_speaker()
            sid = str(args[0]).strip()
            if sid and sid.lower() != "end":
                body_lines.append(f"[CG Still: {sid}]")
        elif name == "movie" and args:
            flush_speaker()
            body_lines.append(f"[Movie: {str(args[0]).strip()}]")

    flush_speaker()

    header: list[str] = []
    if title:
        header.append(f"# {title}")
    if outline:
        header.append(outline)
    if header:
        header.append("")
    return "\n".join(header + body_lines).rstrip() + "\n"


def _generate_story_transcripts(script_paths: list[Path], overwrite: bool = False) -> int:
    written = 0
    for json_path in script_paths:
        if not json_path.exists() or json_path.stat().st_size == 0:
            continue
        txt_path = json_path.with_suffix(".txt")
        if not overwrite and txt_path.exists() and txt_path.stat().st_size > 0:
            continue
        try:
            text = _story_json_to_text(json_path.read_text(encoding="utf-8"))
            tmp = txt_path.with_suffix(".txt.part")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(txt_path)
            written += 1
        except Exception:
            continue
    return written


class PriconneAdapter(GameAdapter):
    code = "priconne"
    name = "Princess Connect! Re:Dive"
    credits = "esterTion (redive.estertion.win / redive_master_db_diff)"
    supported_regions = ("jp",)
    supports_story = True

    _RARITY_MAP = {
        "1": 1,
        "1star": 1,
        "1*": 1,
        "r": 1,
        "3": 3,
        "3star": 3,
        "3*": 3,
        "sr": 3,
        "ssr": 3,
        "6": 6,
        "6star": 6,
        "6*": 6,
        "ur": 6,
    }

    def _read_or_build_cache(self, cache_path: Path, refresh: bool, builder) -> dict[str, Any]:
        if not refresh and cache_path.exists() and cache_path.stat().st_size > 0:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        data = builder()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".json.part")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(cache_path)
        return data

    def _load_card_catalog(self, options: DownloadOptions) -> dict[str, Any]:
        cache_path = self.masterdata_dir(options) / "card_catalog.json"

        def _build() -> dict[str, Any]:
            full_files, full_names = _parse_listing("/card/full/", ".webp")
            prof_files, prof_names = _parse_listing("/card/profile/", ".webp")
            unit_names: dict[str, str] = {}
            for raw_map in (prof_names, full_names):
                for k, v in raw_map.items():
                    if len(k) >= 4:
                        unit_names[k[:4]] = v
            return {
                "full": full_files,
                "profile": prof_files,
                "unit_names": unit_names,
            }

        return self._read_or_build_cache(cache_path, options.refresh_masterdata, _build)

    def _load_story_catalog(self, options: DownloadOptions) -> dict[str, Any]:
        cache_path = self.masterdata_dir(options) / "story_catalog.json"

        def _build() -> dict[str, Any]:
            stills, still_names = _parse_listing("/card/story/", ".webp")
            data_groups, data_unit_names = _parse_story_data_groups()
            # Merge unit names from /card/full/ as well so newer 13xx/14xx characters resolve cleanly
            _, full_names = _parse_listing("/card/full/", ".webp")
            unit_names: dict[str, str] = {}
            for k, v in full_names.items():
                if len(k) >= 4:
                    unit_names[k[:4]] = v
            for k, v in still_names.items():
                if k[:2] in _BOND_PREFIXES and len(k) >= 4:
                    unit_names[k[:4]] = v
            unit_names.update(data_unit_names)

            story_names = {
                k: v for k, v in still_names.items() if k[:2] not in _BOND_PREFIXES
            }
            for grp in data_groups:
                gid = grp["group_id"]
                if gid[:2] not in _BOND_PREFIXES and grp["group_name"]:
                    story_names.setdefault(gid, grp["group_name"])

            return {
                "stills": stills,
                "unit_names": unit_names,
                "story_names": story_names,
                "data_groups": data_groups,
            }

        return self._read_or_build_cache(cache_path, options.refresh_masterdata, _build)

    def _load_char_catalog(self, options: DownloadOptions) -> dict[str, Any]:
        cache_path = self.masterdata_dir(options) / "char_catalog.json"

        def _build() -> dict[str, Any]:
            profile, p_names = _parse_listing("/card/profile/", ".webp")
            actual_profile, a_names = _parse_listing("/card/actual_profile/", ".webp")
            icon_unit, i_names = _parse_listing("/icon/unit/", ".webp")
            plate, pl_names = _parse_listing("/icon/plate/", ".webp")
            unit_names: dict[str, str] = {}
            for raw_map in (p_names, a_names, i_names, pl_names):
                for k, v in raw_map.items():
                    if len(k) >= 4:
                        unit_names[k[:4]] = v
            return {
                "profile": profile,
                "actual_profile": actual_profile,
                "icon_unit": icon_unit,
                "plate": plate,
                "unit_names": unit_names,
            }

        return self._read_or_build_cache(cache_path, options.refresh_masterdata, _build)

    def run_category(self, category: str, options: DownloadOptions) -> CategoryResult:
        if category == "live2d":
            return CategoryResult(
                game=self.code,
                category=category,
                supported=False,
                note="Princess Connect! Re:Dive ใช้โมเดล Spine ไม่มี Live2D — รองรับหมวด card, story, bond_story, character",
            )

        threads = max(1, min(options.threads, 24))
        if category == "card":
            return self._download_cards(options, threads)
        if category == "story":
            return self._download_stories(options, threads)
        if category == "bond_story":
            return self._download_bond_stories(options, threads)
        if category == "character":
            return self._download_characters(options, threads)

        return CategoryResult(
            game=self.code,
            category=category,
            supported=False,
            note=f"Unknown category: {category}",
        )

    def _download_cards(self, options: DownloadOptions, threads: int) -> CategoryResult:
        cat = self._load_card_catalog(options)
        unit_names: dict[str, str] = cat.get("unit_names", {})
        target_rar = self._RARITY_MAP.get((options.rarity or "").lower())
        q = (options.character or "").strip().lower()
        base_out = self.game_dir(options) / "card"

        tasks: list[DownloadTask] = []
        # Full-res 1408x792 cards (3* and 6*)
        for fname in cat.get("full", []):
            stem = fname.rsplit(".", 1)[0]
            if len(stem) != 6 or not stem.isdigit():
                continue
            unit4 = stem[:4]
            rar = int(stem[4])
            if target_rar and rar != target_rar:
                continue
            cname = unit_names.get(unit4, "")
            if q and q not in stem and q not in unit4 and q not in cname.lower():
                continue
            slug = f"_{sanitize_filename(cname)}" if cname else ""
            tasks.append(
                DownloadTask(
                    url=f"{REDIVE_BASE}/card/full/{fname}",
                    dest=base_out / "full" / f"{stem}_r{rar}{slug}.webp",
                )
            )

        # Base 1* card illustrations (1024x682; only available under /card/profile/)
        for fname in cat.get("profile", []):
            stem = fname.rsplit(".", 1)[0]
            if len(stem) != 6 or not stem.isdigit() or stem[4] != "1":
                continue
            unit4 = stem[:4]
            rar = 1
            if target_rar and rar != target_rar:
                continue
            cname = unit_names.get(unit4, "")
            if q and q not in stem and q not in unit4 and q not in cname.lower():
                continue
            slug = f"_{sanitize_filename(cname)}" if cname else ""
            tasks.append(
                DownloadTask(
                    url=f"{REDIVE_BASE}/card/profile/{fname}",
                    dest=base_out / "base_1star" / f"{stem}_r1{slug}.webp",
                )
            )

        if options.limit:
            tasks = tasks[: options.limit]

        return run_download_tasks(
            tasks,
            game=self.code,
            category="card",
            output_path=base_out,
            threads=threads,
            note="Card Full 1408x792 (3★/6★) + Base 1★ 1024x682 (.webp) จาก redive.estertion.win",
            cache_404_path=None if options.refresh_masterdata else (base_out.parent / ".card_404_urls.json"),
        )

    def _download_stories(self, options: DownloadOptions, threads: int) -> CategoryResult:
        cat = self._load_story_catalog(options)
        story_names: dict[str, str] = cat.get("story_names", {})
        q = (options.character or "").strip().lower()
        base_out = self.game_dir(options) / "story"

        still_tasks: list[DownloadTask] = []
        for fname in cat.get("stills", []):
            if fname[:2] in _BOND_PREFIXES:
                continue
            gid = fname[:4]
            sname = story_names.get(gid, "")
            if q and q not in fname.lower() and q not in gid and q not in sname.lower():
                continue
            bucket = _story_bucket(gid)
            gfolder = f"{gid}_{sanitize_filename(sname)}" if sname else gid
            still_tasks.append(
                DownloadTask(
                    url=f"{REDIVE_BASE}/card/story/{fname}",
                    dest=base_out / "stills" / bucket / gfolder / fname,
                )
            )

        script_tasks: list[DownloadTask] = []
        for grp in cat.get("data_groups", []):
            gid = grp["group_id"]
            if gid[:2] in _BOND_PREFIXES:
                continue
            sname = grp.get("group_name") or story_names.get(gid, "")
            if q and q not in gid.lower() and q not in sname.lower():
                matching_files = [f for f in grp["files"] if q in f.lower()]
                if not matching_files:
                    continue
            else:
                matching_files = grp["files"]
            bucket = _story_bucket(gid)
            gfolder = f"{gid}_{sanitize_filename(sname)}" if sname else gid
            for fname in matching_files:
                script_tasks.append(
                    DownloadTask(
                        url=f"{REDIVE_BASE}/story/data/{fname}",
                        dest=base_out / "scripts" / bucket / gfolder / fname,
                    )
                )

        if options.limit:
            still_tasks = still_tasks[: options.limit]
            script_tasks = script_tasks[: options.limit]

        all_tasks = still_tasks + script_tasks
        res = run_download_tasks(
            all_tasks,
            game=self.code,
            category="story",
            output_path=base_out,
            threads=threads,
            cache_404_path=None if options.refresh_masterdata else (base_out.parent / ".story_404_urls.json"),
        )
        written = _generate_story_transcripts(
            [t.dest for t in script_tasks],
            overwrite=options.refresh_masterdata,
        )
        res.note = (
            f"Main/Event/Guild/Tower/Anniv Story: {len(still_tasks)} CG stills + "
            f"{len(script_tasks)} script JSONs ({written} new .txt transcripts)"
        )
        return res

    def _download_bond_stories(self, options: DownloadOptions, threads: int) -> CategoryResult:
        cat = self._load_story_catalog(options)
        unit_names: dict[str, str] = cat.get("unit_names", {})
        q = (options.character or "").strip().lower()
        base_out = self.game_dir(options) / "bond_story"

        still_tasks: list[DownloadTask] = []
        for fname in cat.get("stills", []):
            if fname[:2] not in _BOND_PREFIXES:
                continue
            char4 = fname[:4]
            cname = unit_names.get(char4, "")
            if q and q not in fname.lower() and q not in char4 and q not in cname.lower():
                continue
            cfolder = f"{char4}_{sanitize_filename(cname)}" if cname else char4
            still_tasks.append(
                DownloadTask(
                    url=f"{REDIVE_BASE}/card/story/{fname}",
                    dest=base_out / "stills" / cfolder / fname,
                )
            )

        script_tasks: list[DownloadTask] = []
        for grp in cat.get("data_groups", []):
            gid = grp["group_id"]
            if gid[:2] not in _BOND_PREFIXES:
                continue
            char4 = gid[:4]
            cname = grp.get("group_name") or unit_names.get(char4, "")
            if q and q not in char4.lower() and q not in cname.lower():
                matching_files = [f for f in grp["files"] if q in f.lower()]
                if not matching_files:
                    continue
            else:
                matching_files = grp["files"]
            cfolder = f"{char4}_{sanitize_filename(cname)}" if cname else char4
            for fname in matching_files:
                script_tasks.append(
                    DownloadTask(
                        url=f"{REDIVE_BASE}/story/data/{fname}",
                        dest=base_out / "scripts" / cfolder / fname,
                    )
                )

        if options.limit:
            still_tasks = still_tasks[: options.limit]
            script_tasks = script_tasks[: options.limit]

        all_tasks = still_tasks + script_tasks
        res = run_download_tasks(
            all_tasks,
            game=self.code,
            category="bond_story",
            output_path=base_out,
            threads=threads,
            cache_404_path=None if options.refresh_masterdata else (base_out.parent / ".bond_story_404_urls.json"),
        )
        written = _generate_story_transcripts(
            [t.dest for t in script_tasks],
            overwrite=options.refresh_masterdata,
        )
        res.note = (
            f"Character Bond Story: {len(still_tasks)} CG stills + "
            f"{len(script_tasks)} script JSONs ({written} new .txt transcripts)"
        )
        return res

    def _download_characters(self, options: DownloadOptions, threads: int) -> CategoryResult:
        cat = self._load_char_catalog(options)
        unit_names: dict[str, str] = cat.get("unit_names", {})
        q = (options.character or "").strip().lower()
        base_out = self.game_dir(options) / "character"

        tasks: list[DownloadTask] = []
        buckets = (
            ("profile", "/card/profile/"),
            ("actual_profile", "/card/actual_profile/"),
            ("icon_unit", "/icon/unit/"),
            ("plate", "/icon/plate/"),
        )
        for subfolder, url_prefix in buckets:
            for fname in cat.get(subfolder, []):
                stem = fname.rsplit(".", 1)[0]
                unit4 = stem[:4]
                cname = unit_names.get(unit4, "")
                if q and q not in stem.lower() and q not in unit4 and q not in cname.lower():
                    continue
                slug = f"_{sanitize_filename(cname)}" if cname else ""
                tasks.append(
                    DownloadTask(
                        url=f"{REDIVE_BASE}{url_prefix}{fname}",
                        dest=base_out / subfolder / f"{stem}{slug}.webp",
                    )
                )

        if options.limit:
            tasks = tasks[: options.limit]

        return run_download_tasks(
            tasks,
            game=self.code,
            category="character",
            output_path=base_out,
            threads=threads,
            note="Character Profiles (Normal/Real World), Unit Icons & Plates (.webp)",
            cache_404_path=None if options.refresh_masterdata else (base_out.parent / ".character_404_urls.json"),
        )
