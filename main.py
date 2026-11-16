"""Unified CLI for the multi-game anime/gacha Masterdata & Asset Downloader."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.base import CATEGORIES, CategoryResult, DownloadOptions
from core.drive_sync import DriveSyncClient, DriveSyncError
from games import ADAPTERS

DEFAULT_DRIVE_PARENT_ID = "1kaSiYfkeaFXvXQQbZlFKJV4Tq--M5yFf"
DEFAULT_DRIVE_ROOT_NAME = "AnimeGameAssets"


def parse_games(raw_games: list[str]) -> list[str]:
    tokens: list[str] = []
    for item in raw_games:
        for part in item.split(","):
            tok = part.strip().lower()
            if tok:
                tokens.append(tok)
    if not tokens:
        raise ValueError("Please specify at least one --game code or 'all'.")
    if "all" in tokens:
        return list(ADAPTERS.keys())
    unknown = [t for t in tokens if t not in ADAPTERS]
    if unknown:
        valid = ", ".join(["all", *ADAPTERS.keys()])
        raise ValueError(f"Unknown game code(s): {', '.join(unknown)}. Valid choices: {valid}")
    # Preserve order without duplicates
    seen: set[str] = set()
    ordered: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def print_games_table() -> None:
    print("Supported Games:")
    print("-" * 96)
    print(f"{'Code':<14} {'Regions':<18} {'Name':<44} {'Sources / Credits'}")
    print("-" * 96)
    for code, adapter in ADAPTERS.items():
        regs = ",".join(adapter.supported_regions)
        print(f"{code:<14} {regs:<18} {adapter.name[:43]:<44} {adapter.credits}")
    print("-" * 96)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="anime-dl",
        description="Multi-game Anime/Gacha Masterdata & Asset Downloader with Google Drive sync",
    )
    p.add_argument(
        "--list-games",
        action="store_true",
        help="Show all supported games and data sources, then exit",
    )
    p.add_argument(
        "--game",
        nargs="+",
        default=["all"],
        help=f"Game code(s) to download, comma/space separated or 'all' (choices: all, {', '.join(ADAPTERS)})",
    )
    p.add_argument(
        "--category",
        choices=("card", "live2d", "character", "all"),
        default="all",
        help="Asset category: card (full-res cards), live2d (Live2D/Spine), character (sprites/icons/trims), or all",
    )
    p.add_argument(
        "--region",
        default="jp",
        help="Server region where supported (e.g., jp, en, tw, hk-tw-mo, kr, cn). Default: jp",
    )
    p.add_argument(
        "--rarity",
        default=None,
        help="Optional rarity filter (e.g., n, r, sr, ssr, ur, 3, 4, 5)",
    )
    p.add_argument(
        "--character",
        default=None,
        help="Optional character name / ID substring filter",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit items per game/category (great for testing or sampling)",
    )
    p.add_argument(
        "--threads",
        type=int,
        default=8,
        help="Concurrent download threads (default: 8)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("./downloads"),
        help="Local output directory for downloaded assets (default: ./downloads)",
    )
    p.add_argument(
        "--refresh-masterdata",
        action="store_true",
        help="Force re-fetch cached masterdata JSON & asset catalogs",
    )
    p.add_argument(
        "--upload-drive",
        action="store_true",
        help="Sync downloaded assets to Google Drive after each category completes",
    )
    p.add_argument(
        "--drive-parent-id",
        default=DEFAULT_DRIVE_PARENT_ID,
        help=f"Google Drive parent folder ID (default: {DEFAULT_DRIVE_PARENT_ID})",
    )
    p.add_argument(
        "--drive-root-name",
        default=DEFAULT_DRIVE_ROOT_NAME,
        help=f"Subfolder name created inside parent Drive folder (default: {DEFAULT_DRIVE_ROOT_NAME})",
    )
    p.add_argument(
        "--drive-mode",
        choices=("auto", "direct", "zip"),
        default="auto",
        help="Drive upload mode: direct (individual files), zip (packed archive), or auto (direct <= 40 files else zip)",
    )
    p.add_argument(
        "--cleanup-local",
        action="store_true",
        help="Delete local category files after successful upload to Google Drive (saves disk space)",
    )
    p.add_argument(
        "--overwrite-drive",
        action="store_true",
        help="Overwrite existing files of the same name in Google Drive",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_games:
        print_games_table()
        return 0

    try:
        games = parse_games(args.game)
    except ValueError as exc:
        parser.error(str(exc))

    categories = list(CATEGORIES) if args.category == "all" else [args.category]
    options = DownloadOptions(
        out_dir=args.out_dir.resolve(),
        categories=categories,
        region=args.region,
        rarity=args.rarity,
        character=args.character,
        limit=args.limit,
        threads=args.threads,
        refresh_masterdata=args.refresh_masterdata,
    )

    drive_client: DriveSyncClient | None = None
    if args.upload_drive:
        try:
            drive_client = DriveSyncClient(
                parent_id=args.drive_parent_id,
                root_name=args.drive_root_name,
            )
            root_url = drive_client.root_folder_url()
            print(f"[Drive] Connected -> {root_url}")
        except DriveSyncError as exc:
            print(f"[Drive Error] {exc}", file=sys.stderr)
            return 2

    results: list[tuple[CategoryResult, dict | None]] = []
    for gcode in games:
        adapter = ADAPTERS[gcode]
        print(f"\n=== [{gcode}] {adapter.name} (region={options.region}) ===")
        for cat in categories:
            try:
                res = adapter.run_category(cat, options)
            except Exception as exc:
                res = CategoryResult(
                    game=gcode,
                    category=cat,
                    supported=True,
                    failed=1,
                    note=f"Error: {exc}",
                    errors=[str(exc)],
                )
            sync_info = None
            if drive_client and res.supported and res.output_path and res.output_path.exists():
                drive_cat = res.output_path.name
                try:
                    sync_info = drive_client.sync_category_dir(
                        local_dir=res.output_path,
                        game_code=gcode,
                        category=drive_cat,
                        mode=args.drive_mode,
                        cleanup_local=args.cleanup_local,
                        overwrite=args.overwrite_drive,
                    )
                    print(
                        f"[Drive] {gcode}/{drive_cat} -> {sync_info.get('status')} "
                        f"(mode={sync_info.get('mode')}, uploaded={sync_info.get('uploaded')}, "
                        f"skipped={sync_info.get('skipped')}) {sync_info.get('folder_url', '')}"
                    )
                except DriveSyncError as exc:
                    print(f"[Drive Error] Failed syncing {gcode}/{drive_cat}: {exc}", file=sys.stderr)
                    res.failed += 1
                    res.errors.append(str(exc))
            results.append((res, sync_info))

    print("\n" + "=" * 96)
    print("SUMMARY")
    print("=" * 96)
    any_failed = False
    for res, sync_info in results:
        if res.failed > 0:
            any_failed = True
        status = "UNSUPPORTED" if not res.supported else ("ERR" if res.failed else "OK")
        line = (
            f"- {res.game:<12} | {res.category:<10} | {status:<11} | "
            f"dl={res.downloaded:<4} skip={res.skipped:<4} fail={res.failed:<3} total={res.total:<4}"
        )
        if res.note:
            line += f" | {res.note}"
        print(line)
        if sync_info and sync_info.get("folder_url"):
            print(f"    Drive: {sync_info['folder_url']} (mode={sync_info.get('mode')}, up={sync_info.get('uploaded')}, skip={sync_info.get('skipped')})")
        for err in res.errors[:3]:
            print(f"    ! {err}")

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
