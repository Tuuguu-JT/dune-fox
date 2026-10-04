"""Start/stop FlySync poll thread and feed the main program intents + status."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Callable, Iterable

from . import xinput
from .types import (
    BUTTON_ACTION,
    CHORDS,
    Axes,
    Edge,
    Held,
    Intent,
    LinkEvent,
    LinkState,
    PadStatus,
)

LinkCallback = Callable[[LinkEvent], None]


class DuneFox:
    """
    Plug-in pad reader.

        fox = DuneFox()
        fox.start()                 # background thread
        intents = fox.take_intents()
        axes = fox.axes()
        st = fox.status()
        fox.stop()                  # pause polling
        fox.start()                 # resume
    """

    def __init__(
        self,
        *,
        slot: int | None = None,
        hz: float = 125.0,
        stick_dead: float = 0.08,
        trigger_dead: float = 0.04,
        hold_s: float = 0.40,
        double_s: float = 0.28,
        miss_limit: int = 8,
        stale_s: float = 0.45,
        battery_period_s: float = 2.0,
        auto_reconnect: bool = True,
        on_link: LinkCallback | None = None,
        actions: dict[str, str] | None = None,
    ) -> None:
        self.slot_pref = slot
        self.hz = max(10.0, hz)
        self.stick_dead = stick_dead
        self.trigger_dead = trigger_dead
        self.hold_s = hold_s
        self.double_s = double_s
        self.miss_limit = max(2, miss_limit)
        self.stale_s = stale_s
        self.battery_period_s = battery_period_s
        self.auto_reconnect = auto_reconnect
        self._on_link = on_link
        self.actions = dict(BUTTON_ACTION if actions is None else actions)

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._dll = None
        self._slot = 0 if slot is None else slot

        self._intents: deque[Intent] = deque(maxlen=256)
        self._link_q: deque[LinkEvent] = deque(maxlen=64)
        self._seq = 0
        self._link_seq = 0
        self._held = Held()
        self._prev_buttons: dict[str, bool] = {}
        self._lt_down = False
        self._rt_down = False
        self._flick_arm: tuple[float, float, float] | None = None
        self._chords_live: set[str] = set()
        self._packet = 0
        self._packet_t = 0.0
        self._miss = 0
        self._reconnects = 0
        self._last_error = ""
        self._last_seen = 0.0
        self._bat_kind = "unknown"
        self._bat_level = "unknown"
        self._bat_frac = -1.0
        self._bat_t = 0.0
        self._axes = Axes()
        self._link = LinkState.STOPPED
        self._link_since = time.perf_counter()

    # ----- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="dune-fox", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 1.5) -> None:
        self._stop.set()
        th = self._thread
        if th is not None and th.is_alive() and threading.current_thread() is not th:
            th.join(timeout)
        with self._lock:
            self._thread = None
            self._axes = Axes(t=time.perf_counter())
            self._set_link(LinkState.STOPPED, "polling stopped")

    def is_running(self) -> bool:
        th = self._thread
        return th is not None and th.is_alive()

    def __enter__(self) -> DuneFox:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # ----- main-loop reads ---------------------------------------------------

    def take_intents(self) -> list[Intent]:
        """Drain discrete presses / chords / flicks since last call. Never blocks."""
        with self._lock:
            out = list(self._intents)
            self._intents.clear()
            return out

    def axes(self) -> Axes:
        """Current sticks and triggers. Safe while the thread is stopped (zeros)."""
        with self._lock:
            return self._axes

    def status(self) -> PadStatus:
        """Battery and link health. Independent of take_intents()."""
        with self._lock:
            return PadStatus(
                connected=self._link in (LinkState.LIVE, LinkState.STALE),
                link=self._link,
                polling=self.is_running(),
                slot=self._slot,
                backend="xinput",
                packet=self._packet,
                battery_kind=self._bat_kind,
                battery_level=self._bat_level,
                battery_frac=self._bat_frac,
                last_error=self._last_error,
                last_seen_s=self._last_seen,
                reconnects=self._reconnects,
                miss_streak=self._miss,
            )

    def refresh_status(self) -> PadStatus:
        """Hit XInput battery now (main thread). Cheap; still OK to call rarely."""
        dll = self._dll
        if dll is None:
            try:
                dll = xinput.load_dll()
                self._dll = dll
            except OSError as exc:
                with self._lock:
                    self._last_error = str(exc)
                return self.status()
        slot = self._slot
        kind, level, frac = xinput.battery(dll, slot)
        with self._lock:
            self._bat_kind, self._bat_level, self._bat_frac = kind, level, frac
            self._bat_t = time.perf_counter()
        return self.status()

    def take_link_events(self) -> list[LinkEvent]:
        with self._lock:
            out = list(self._link_q)
            self._link_q.clear()
            return out

    def wait_connected(self, timeout: float = 5.0) -> bool:
        deadline = time.perf_counter() + timeout
        if not self.is_running():
            self.start()
        while time.perf_counter() < deadline:
            if self.status().link == LinkState.LIVE:
                return True
            time.sleep(0.05)
        return False

    def on_link(self, cb: LinkCallback | None) -> None:
        self._on_link = cb

    # ----- thread ------------------------------------------------------------

    def _run(self) -> None:
        try:
            self._dll = xinput.load_dll()
        except OSError as exc:
            with self._lock:
                self._last_error = str(exc)
            self._set_link(LinkState.LOST, str(exc))
            return

        self._set_link(LinkState.SEARCHING, "looking for FlySync / XInput pad")
        dt = 1.0 / self.hz
        while not self._stop.is_set():
            t0 = time.perf_counter()
            self._tick(t0)
            time.sleep(max(0.0, dt - (time.perf_counter() - t0)))

    def _tick(self, now: float) -> None:
        dll = self._dll
        assert dll is not None
        err, st = xinput.get_state(dll, self._slot)
        if err != 0:
            alt = xinput.first_slot(dll, self.slot_pref)
            if alt is not None:
                self._slot = alt
                err, st = xinput.get_state(dll, self._slot)
        if err != 0 or st is None:
            self._on_miss(now, err)
            return
        self._on_frame(now, st)

    def _on_miss(self, now: float, err: int) -> None:
        with self._lock:
            self._miss += 1
            self._last_error = (
                "device not connected" if err == xinput.ERROR_DEVICE_NOT_CONNECTED else f"xinput {err}"
            )
            miss = self._miss
        if miss >= 2:
            self._zero_controls(now)
        if miss < self.miss_limit:
            return
        if self._link != LinkState.LOST:
            self._set_link(LinkState.LOST, self._last_error)
        if not self.auto_reconnect:
            self._stop.set()
            return
        if self._link != LinkState.SEARCHING:
            self._set_link(LinkState.SEARCHING, "waiting for pad")
        time.sleep(0.15)

    def _on_frame(self, now: float, st: xinput.XINPUT_STATE) -> None:
        g = st.Gamepad
        pkt = int(st.dwPacketNumber)
        buttons = xinput.buttons_from(int(g.wButtons))
        axes = Axes(
            lx=xinput.norm_axis(g.sThumbLX, self.stick_dead),
            ly=xinput.norm_axis(g.sThumbLY, self.stick_dead),
            rx=xinput.norm_axis(g.sThumbRX, self.stick_dead),
            ry=xinput.norm_axis(g.sThumbRY, self.stick_dead),
            lt=xinput.norm_trigger(g.bLeftTrigger, self.trigger_dead),
            rt=xinput.norm_trigger(g.bRightTrigger, self.trigger_dead),
            t=now,
        )
        with self._lock:
            was_lost = self._link in (LinkState.LOST, LinkState.SEARCHING, LinkState.STOPPED)
            if self._miss >= self.miss_limit:
                self._reconnects += 1
            self._miss = 0
            self._last_error = ""
            self._last_seen = now
            if pkt != self._packet:
                self._packet = pkt
                self._packet_t = now
            self._axes = axes
            prev = self._prev_buttons
            self._prev_buttons = buttons
            self._held.buttons = buttons

        if was_lost or self._link != LinkState.LIVE:
            if was_lost:
                self._set_link(LinkState.LIVE, f"slot {self._slot}")
            elif now - self._packet_t > self.stale_s:
                self._set_link(LinkState.STALE, "packet frozen")
            else:
                self._set_link(LinkState.LIVE, "")

        if now - self._packet_t > self.stale_s and self._link == LinkState.LIVE:
            self._set_link(LinkState.STALE, "packet frozen")
        elif now - self._packet_t <= self.stale_s and self._link == LinkState.STALE:
            self._set_link(LinkState.LIVE, "packet moving")

        self._emit_buttons(now, prev, buttons)
        self._emit_triggers(now, axes)
        self._emit_flick(now, axes)
        self._maybe_battery(now)

    def _zero_controls(self, now: float) -> None:
        with self._lock:
            prev = self._prev_buttons
            self._prev_buttons = {}
            self._axes = Axes(t=now)
            self._held = Held()
            self._lt_down = False
            self._rt_down = False
            self._flick_arm = None
            self._chords_live.clear()
        for name, on in prev.items():
            if on:
                self._push_intent(now, name, Edge.UP, held_ms=0)

    def _maybe_battery(self, now: float) -> None:
        if now - self._bat_t < self.battery_period_s:
            return
        dll = self._dll
        if dll is None:
            return
        kind, level, frac = xinput.battery(dll, self._slot)
        with self._lock:
            self._bat_kind, self._bat_level, self._bat_frac = kind, level, frac
            self._bat_t = now

    def _emit_buttons(self, now: float, prev: dict[str, bool], cur: dict[str, bool]) -> None:
        mods = tuple(sorted(n for n in ("LB", "RB") if cur.get(n)))
        for name in xinput.BUTTON_MAP:
            key = name[0]
            before, after = prev.get(key, False), cur.get(key, False)
            if after and not before:
                is_double = (
                    key == self._held.last_up_button
                    and (now - self._held.last_up_t) <= self.double_s
                )
                self._held.down_t = now
                self._held.last_down = key
                self._held.hold_emitted = False
                edge = Edge.DOUBLE if is_double else Edge.DOWN
                self._push_intent(now, key, edge, modifiers=mods)
                self._maybe_chord(now, cur, key)
            elif before and not after:
                held_ms = int((now - self._held.down_t) * 1000) if key == self._held.last_down else 0
                self._held.last_up_t = now
                self._held.last_up_button = key
                self._push_intent(now, key, Edge.UP, held_ms=held_ms, modifiers=mods)
            elif (
                after
                and key == self._held.last_down
                and not self._held.hold_emitted
                and self._held.down_t
                and now - self._held.down_t >= self.hold_s
            ):
                self._held.hold_emitted = True
                self._push_intent(
                    now,
                    key,
                    Edge.HOLD,
                    held_ms=int(self.hold_s * 1000),
                    modifiers=mods,
                )

    def _maybe_chord(self, now: float, cur: dict[str, bool], just: str) -> None:
        down = frozenset(k for k, v in cur.items() if v)
        live: set[str] = set()
        for keys, action in CHORDS.items():
            if keys <= down:
                live.add(action)
                if action not in self._chords_live and just in keys:
                    self._chords_live.add(action)
                    self._push(
                        Intent(
                            seq=self._next_seq(),
                            t=now,
                            action=action,
                            edge=Edge.DOWN,
                            button="+".join(sorted(keys)),
                            chord=tuple(sorted(keys)),
                            modifiers=tuple(sorted(n for n in ("LB", "RB") if cur.get(n))),
                        )
                    )
        self._chords_live &= live

    def _emit_triggers(self, now: float, axes: Axes) -> None:
        for which, val, flag in (("LT", axes.lt, "_lt_down"), ("RT", axes.rt, "_rt_down")):
            down = getattr(self, flag)
            if not down and val >= 0.55:
                setattr(self, flag, True)
                self._push_intent(now, which, Edge.CLICK, x=val)
            elif down and val <= 0.35:
                setattr(self, flag, False)
                self._push_intent(now, which, Edge.UP, x=val)

    def _emit_flick(self, now: float, axes: Axes) -> None:
        mag = math.hypot(axes.lx, axes.ly)
        if mag >= 0.85:
            self._flick_arm = (now, axes.lx, axes.ly)
            return
        arm = self._flick_arm
        if arm is None:
            return
        t, x, y = arm
        if mag <= 0.35 and (now - t) <= 0.18:
            hx, hy = _octant(x, y)
            self._push(
                Intent(
                    seq=self._next_seq(),
                    t=now,
                    action="flick",
                    edge=Edge.FLICK,
                    button="LS",
                    x=hx,
                    y=hy,
                )
            )
        if mag <= 0.35 or (now - t) > 0.18:
            self._flick_arm = None

    def _push_intent(
        self,
        now: float,
        button: str,
        edge: Edge,
        held_ms: int = 0,
        modifiers: tuple[str, ...] = (),
        x: float = 0.0,
        y: float = 0.0,
    ) -> None:
        action = {
            "LT": "brake",
            "RT": "boost",
        }.get(button, self.actions.get(button, button.lower()))
        self._push(
            Intent(
                seq=self._next_seq(),
                t=now,
                action=action,
                edge=edge,
                button=button,
                held_ms=held_ms,
                x=x,
                y=y,
                modifiers=modifiers,
            )
        )

    def _push(self, intent: Intent) -> None:
        with self._lock:
            self._intents.append(intent)

    def _next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def _set_link(self, state: LinkState, detail: str) -> None:
        with self._lock:
            if state == self._link and not detail:
                return
            prev = self._link
            if state == prev and detail == "":
                return
            kind = {
                (LinkState.LOST, LinkState.LIVE): "found",
                (LinkState.SEARCHING, LinkState.LIVE): "found",
                (LinkState.STOPPED, LinkState.LIVE): "found",
                (LinkState.STALE, LinkState.LIVE): "recovered",
                (LinkState.LIVE, LinkState.STALE): "stale",
                (LinkState.LIVE, LinkState.LOST): "lost",
                (LinkState.STALE, LinkState.LOST): "lost",
                (LinkState.SEARCHING, LinkState.LOST): "lost",
            }.get((prev, state), state.value)
            self._link = state
            self._link_since = time.perf_counter()
            ev = LinkEvent(
                seq=self._link_seq + 1,
                t=self._link_since,
                kind=kind,
                state=state,
                detail=detail,
            )
            self._link_seq = ev.seq
            self._link_q.append(ev)
            cb = self._on_link
        if cb is not None and prev != state:
            try:
                cb(ev)
            except Exception:
                pass


def _octant(x: float, y: float) -> tuple[float, float]:
    ang = math.atan2(y, x)
    step = round(ang / (math.pi / 4)) * (math.pi / 4)
    return (round(math.cos(step), 3), round(math.sin(step), 3))


def iter_intents(fox: DuneFox, *, idle_s: float = 0.01) -> Iterable[Intent]:
    """Generator for a main loop that only cares about edges."""
    while fox.is_running():
        batch = fox.take_intents()
        if not batch:
            time.sleep(idle_s)
            continue
        yield from batch
