"""Shared data types, download task definitions, and base adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CATEGORIES = ("card", "live2d", "character")


@dataclass
class DownloadTask:
    url: str
    dest: Path
    headers: dict[str, str] = field(default_factory=dict)
    optional: bool = False
    label: str = ""
    reject_html: bool = True


@dataclass
class DownloadOptions:
    out_dir: Path
    categories: list[str]
    region: str = "jp"
    rarity: Optional[str] = None
    character: Optional[str] = None
    limit: Optional[int] = None
    threads: int = 8
    refresh_masterdata: bool = False


@dataclass
class CategoryResult:
    game: str
    category: str
    supported: bool = True
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    output_path: Optional[Path] = None
    note: str = ""
    errors: list[str] = field(default_factory=list)


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Clean string for cross-platform safe directory/file naming."""
    bad = '<>:"/\\|?*\r\n\t'
    out = "".join("_" if ch in bad else ch for ch in str(name))
    out = "_".join(part for part in out.strip().split())
    out = out.strip("._ ")
    if not out:
        return "item"
    return out[:max_len]


class GameAdapter(ABC):
    code: str = ""
    name: str = ""
    credits: str = ""
    supported_regions: tuple[str, ...] = ("jp",)
    category_notes: dict[str, str] = {}

    def game_dir(self, options: DownloadOptions) -> Path:
        return options.out_dir / self.code

    def masterdata_dir(self, options: DownloadOptions) -> Path:
        d = self.game_dir(options) / "masterdata"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @abstractmethod
    def run_category(self, category: str, options: DownloadOptions) -> CategoryResult:
        """Execute asset downloading for a single category (`card`, `live2d`, `character`)."""
        raise NotImplementedError
