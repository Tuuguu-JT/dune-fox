#!/usr/bin/env python3
"""Poll the Dune Fox from the main loop."""

from __future__ import annotations

import time

from dune_fox import DuneFox, Pad

# Every field is fixed width so the line does not jump.
_LINE = (
    "A:{A} B:{B} X:{X} Y:{Y} "
    "LB:{LB} RB:{RB} LS:{LS} RS:{RS} "
    "ST:{START} BK:{BACK} "
    "U:{DPAD_U} D:{DPAD_D} L:{DPAD_L} R:{DPAD_R} "
    "LX:{lx:+.2f} LY:{ly:+.2f} RX:{rx:+.2f} RY:{ry:+.2f} "
    "LT:{lt:.2f} RT:{rt:.2f}"
)
_WIDTH = len(
    _LINE.format(
        A=0, B=0, X=0, Y=0,
        LB=0, RB=0, LS=0, RS=0,
        START=0, BACK=0,
        DPAD_U=0, DPAD_D=0, DPAD_L=0, DPAD_R=0,
        lx=0.0, ly=0.0, rx=0.0, ry=0.0,
        lt=0.0, rt=0.0,
    )
)
_OFFLINE = "no FlySync pad".ljust(_WIDTH)


def _show(pad: Pad) -> str:
    return _LINE.format(
        A=int(pad.A),
        B=int(pad.B),
        X=int(pad.X),
        Y=int(pad.Y),
        LB=int(pad.LB),
        RB=int(pad.RB),
        LS=int(pad.LS),
        RS=int(pad.RS),
        START=int(pad.START),
        BACK=int(pad.BACK),
        DPAD_U=int(pad.DPAD_U),
        DPAD_D=int(pad.DPAD_D),
        DPAD_L=int(pad.DPAD_L),
        DPAD_R=int(pad.DPAD_R),
        lx=pad.lx,
        ly=pad.ly,
        rx=pad.rx,
        ry=pad.ry,
        lt=pad.lt,
        rt=pad.rt,
    )


def main() -> None:
    fox = DuneFox()
    try:
        while True:
            if not fox.connected():
                print(_OFFLINE, end="\r", flush=True)
                time.sleep(0.5)
                continue
            pad = fox.poll()
            if pad is None:
                print(_OFFLINE, end="\r", flush=True)
                time.sleep(0.05)
                continue
            print(_show(pad), end="\r", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
