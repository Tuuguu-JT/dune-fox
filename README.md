# dune-fox

Plug-and-play reader for the **FLYDIGI Dune Fox** over the **FlySync** 2.4 GHz dongle (or USB-C). On Windows the dongle is an XInput / Xbox 360 pad.

Copy the `dune_fox` package next to your app, or `pip install -e .` from this folder.

## Host API

```python
from dune_fox import DuneFox, Edge

fox = DuneFox(hz=125)   # daemon thread, start/stop anytime
fox.start()
fox.wait_connected(5)

axes = fox.axes()                 # analog: move/look/triggers
for it in fox.take_intents():     # discrete: tap, hold, chord, flick
    if it.action == "confirm" and it.edge is Edge.DOWN:
        ...
    if it.action == "estop":
        ...

st = fox.status()                 # battery + link — separate from buttons
if not st.connected:
    ...
if st.charged:
    ...

fox.stop()                        # no more USB polls
fox.start()                       # resume
```

| Call | Use |
| --- | --- |
| `start()` / `stop()` | Poll thread. Stop when the pad is not needed. |
| `take_intents()` | Drain events since last read (taps are not lost if the host is slower than 125 Hz). |
| `axes()` | Latest sticks / triggers for continuous drive. |
| `status()` / `refresh_status()` | Battery, slot, link state. |
| `take_link_events()` / `on_link` | Disconnect / reconnect. |
| `wait_connected(timeout)` | Startup gate. |

### Intent actions

| Pad | `action` | Notes |
| --- | --- | --- |
| A / B / X / Y | `confirm` `cancel` `tool` `option` | `edge`: `down` `up` `hold` `double` |
| D-pad | `jog_n` `jog_s` `jog_w` `jog_e` | |
| LB / RB | `shift` `alt` | also `modifiers` on other intents |
| LS / RS click | `grip_l` `grip_r` | |
| LT / RT | `brake` / `boost` | analog still on `axes()`; event at ~0.55 |
| BACK+START | `estop` | |
| LB+RB | `mode` | |
| left-stick flick | `flick` | `x,y` is 8-way |

Override names with `DuneFox(actions={"A": "grab", ...})`.

## Disconnect handling

1. **Debounce** — a single failed `XInputGetState` is ignored (USB blip). After 8 misses (~60 ms at 125 Hz) the pad is **lost**.
2. **Fail-safe analog** — sticks and triggers go to 0 so the host does not keep the last drive vector.
3. **Held buttons** emit `up` so the host does not think A is still down.
4. **Auto-reconnect** (default) — the thread stays alive and searches slots 0–3 at a lower rate. Host gets `on_link` `found` when the pad returns.
5. **Stale** — `GetState` succeeds but the packet number freezes (dongle present, pad asleep). Treat like a soft disconnect: do not trust analog.
6. **Hard stop** — `auto_reconnect=False` stops the thread on loss; the host calls `start()` when it wants to search again.

Suggested host policy: on `lost` or `stale`, freeze motion; on `found`/`recovered`, require a `confirm` tap before enabling drive.

## Mode

PC X-input: hold **FN + A** until the LED is yellow. Pairing pinhole on the FlySync receiver if it will not bind.

```text
python -m dune_fox.cli --list
python -m dune_fox.cli
python examples/plug_play.py
```
