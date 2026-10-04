from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LinkState(str, Enum):
    SEARCHING = "searching"
    LIVE = "live"
    STALE = "stale"
    LOST = "lost"
    STOPPED = "stopped"


class Edge(str, Enum):
    DOWN = "down"
    UP = "up"
    HOLD = "hold"
    DOUBLE = "double"
    FLICK = "flick"
    CLICK = "click"


# Semantic names the main loop can switch on without caring about A/B/X/Y.
BUTTON_ACTION = {
    "A": "confirm",
    "B": "cancel",
    "X": "tool",
    "Y": "option",
    "START": "menu",
    "BACK": "back",
    "LB": "shift",
    "RB": "alt",
    "LS": "grip_l",
    "RS": "grip_r",
    "DPAD_U": "jog_n",
    "DPAD_D": "jog_s",
    "DPAD_L": "jog_w",
    "DPAD_R": "jog_e",
}

CHORDS = {
    frozenset({"BACK", "START"}): "estop",
    frozenset({"LB", "RB"}): "mode",
    frozenset({"LB", "A"}): "confirm_alt",
    frozenset({"RB", "B"}): "abort_hard",
}


@dataclass(frozen=True, slots=True)
class Axes:
    """Latest analog snapshot. Main drive loop should read this, not the event queue."""

    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    lt: float = 0.0
    rt: float = 0.0
    t: float = 0.0

    @property
    def move(self) -> tuple[float, float]:
        return (self.lx, self.ly)

    @property
    def look(self) -> tuple[float, float]:
        return (self.rx, self.ry)

    @property
    def idle(self) -> bool:
        return max(abs(self.lx), abs(self.ly), abs(self.rx), abs(self.ry), self.lt, self.rt) < 1e-6


@dataclass(frozen=True, slots=True)
class Intent:
    """One discrete thing that happened. Drain with DuneFox.take_intents()."""

    seq: int
    t: float
    action: str
    edge: Edge
    button: str
    held_ms: int = 0
    x: float = 0.0
    y: float = 0.0
    modifiers: tuple[str, ...] = ()
    chord: tuple[str, ...] = ()

    def tagged(self, *names: str) -> bool:
        want = {n.lower() for n in names}
        return self.action.lower() in want or self.button.lower() in want


@dataclass(frozen=True, slots=True)
class PadStatus:
    """Health / battery. Call DuneFox.status() — not mixed into intents."""

    connected: bool
    link: LinkState
    polling: bool
    slot: int
    backend: str
    packet: int
    battery_kind: str
    battery_level: str
    battery_frac: float
    last_error: str
    last_seen_s: float
    reconnects: int
    miss_streak: int

    @property
    def charged(self) -> bool:
        return self.battery_frac >= 0.95 or self.battery_kind == "wired"


@dataclass(frozen=True, slots=True)
class LinkEvent:
    seq: int
    t: float
    kind: str  # found | lost | stale | recovered
    state: LinkState
    detail: str = ""


@dataclass
class Held:
    down_t: float = 0.0
    last_up_t: float = 0.0
    last_up_button: str = ""
    last_down: str = ""
    hold_emitted: bool = False
    buttons: dict[str, bool] = field(default_factory=dict)
