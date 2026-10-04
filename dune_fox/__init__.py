"""Plug-and-play FLYDIGI Dune Fox (FlySync) reader for a host application."""

from .pad import DuneFox, iter_intents
from .types import Axes, Edge, Intent, LinkEvent, LinkState, PadStatus

__all__ = [
    "Axes",
    "DuneFox",
    "Edge",
    "Intent",
    "LinkEvent",
    "LinkState",
    "PadStatus",
    "iter_intents",
]
