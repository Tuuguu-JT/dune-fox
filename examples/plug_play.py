#!/usr/bin/env python3
"""Main loop: poll the library and use the pad data."""

from __future__ import annotations

import time

from dune_fox import Pad, connected, poll


def status(pad: Pad) -> str:
    return (
        f"A:{int(pad.A)} B:{int(pad.B)} X:{int(pad.X)} Y:{int(pad.Y)} "
        f"LB:{int(pad.LB)} RB:{int(pad.RB)} LS:{int(pad.LS)} RS:{int(pad.RS)} "
        f"ST:{int(pad.START)} BK:{int(pad.BACK)} "
        f"U:{int(pad.DPAD_U)} D:{int(pad.DPAD_D)} L:{int(pad.DPAD_L)} R:{int(pad.DPAD_R)} "
        f"LX:{pad.lx:+.2f} LY:{pad.ly:+.2f} RX:{pad.rx:+.2f} RY:{pad.ry:+.2f} "
        f"LT:{pad.lt:.2f} RT:{pad.rt:.2f}"
    )


_OFFLINE = "no FlySync pad".ljust(len(status(Pad())))


def main() -> None:
    try:
        while True:
            pad = poll()
            print(_OFFLINE if not connected() else status(pad), end="\r", flush=True)
            time.sleep(0.05)
    except PermissionError as exc:
        print(exc)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
