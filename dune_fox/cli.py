from __future__ import annotations

import argparse
import sys
import time

from . import xinput
from .pad import DuneFox


def list_devices() -> None:
    print("XInput slots (FlySync dongle enumerates as Xbox 360 Controller):")
    try:
        dll = xinput.load_dll()
    except OSError as exc:
        print(f"  {exc}")
        return
    found = False
    for i in range(4):
        err, st = xinput.get_state(dll, i)
        if err != 0 or st is None:
            continue
        found = True
        kind, level, _frac = xinput.battery(dll, i)
        print(f"  slot {i}: live  battery={kind}/{level}")
    if not found:
        print("  (empty — plug dongle, wake pad, FN+A until LED is yellow)")
    slot = xinput.first_slot(dll)
    if slot is not None:
        print(f"  first live slot: {slot}")


def watch(hz: float, slot: int | None) -> int:
    fox = DuneFox(slot=slot, hz=hz)
    fox.on_link(lambda ev: print(f"\n[link] {ev.kind} -> {ev.state.value}  {ev.detail}"))
    fox.start()
    print(f"Polling {hz:g} Hz. Host uses start()/stop(). Ctrl+C to quit.\n")
    try:
        while True:
            st = fox.status()
            ax = fox.axes()
            intents = fox.take_intents()
            extra = " ".join(f"{i.action}:{i.edge.value}" for i in intents) or "-"
            sys.stdout.write(
                f"\r{st.link.value:10} bat={st.battery_level:6} "
                f"LS={ax.lx:+.2f},{ax.ly:+.2f}  {extra:<40}"
            )
            sys.stdout.flush()
            time.sleep(1.0 / max(10.0, hz))
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        fox.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Dune Fox FlySync utility")
    p.add_argument("--list", action="store_true")
    p.add_argument("--slot", type=int, default=None)
    p.add_argument("--hz", type=float, default=60.0)
    args = p.parse_args(argv)
    if args.list:
        list_devices()
        return 0
    try:
        return watch(args.hz, args.slot)
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
