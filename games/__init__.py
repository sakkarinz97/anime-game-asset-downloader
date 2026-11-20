"""Registry of supported anime/gacha game asset adapters."""

from __future__ import annotations

from core.base import GameAdapter

from .assaultlily import AssaultLilyAdapter
from .bandori import BandoriAdapter
from .cgss import CGSSAdapter
from .holodori import HolodoriAdapter
from .mltd import MLTDAdapter
from .ournotes import OurNotesAdapter
from .pjsk import PJSKAdapter
from .priconne import PriconneAdapter
from .yumesute import YumesuteAdapter

ADAPTERS: dict[str, GameAdapter] = {
    cls.code: cls()
    for cls in (
        CGSSAdapter,
        MLTDAdapter,
        PJSKAdapter,
        HolodoriAdapter,
        BandoriAdapter,
        OurNotesAdapter,
        YumesuteAdapter,
        AssaultLilyAdapter,
        PriconneAdapter,
    )
}
