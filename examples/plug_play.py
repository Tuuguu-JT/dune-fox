#!/usr/bin/env python3
"""Host-side sketch: drop this pattern into the main system."""

from __future__ import annotations

import time

from dune_fox import DuneFox, Edge, LinkState


def on_link(ev) -> None:
    if ev.state is LinkState.LOST:
        print("pad gone — freeze motion, wait for found")
    elif ev.kind == "found":
        print("pad back")


def main() -> None:
    fox = DuneFox(hz=125, on_link=on_link)
    fox.start()
    if not fox.wait_connected(5):
        print("no FlySync pad")
        fox.stop()
        return

    busy = True
    t_end = time.perf_counter() + 8
    while time.perf_counter() < t_end:
        # Pause polling when the host does not need the pad.
        if busy and time.perf_counter() > t_end - 3:
            fox.stop()
            busy = False
            print("stopped thread")
            time.sleep(0.5)
            fox.start()
            print("started thread")

        st = fox.status()
        if st.charged:
            pass  # battery / wired — not mixed into button traffic
        if not st.connected:
            time.sleep(0.05)
            continue

        move_x, move_y = fox.axes().move
        _ = (move_x, move_y)

        for it in fox.take_intents():
            if it.action == "estop":
                print("ESTOP chord")
            elif it.action == "confirm" and it.edge is Edge.DOWN:
                print("ok")
            elif it.action == "flick":
                print("flick", it.x, it.y)
            elif it.tagged("cancel") and it.edge is Edge.DOWN:
                print("cancel")
        time.sleep(0.01)

    fox.stop()


if __name__ == "__main__":
    main()
