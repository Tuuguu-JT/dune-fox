# dune-fox

Poll a **FLYDIGI Dune Fox** over the **FlySync** dongle (or USB-C). On Windows the dongle is an XInput pad.

`pip install -e .` from this folder, then call `poll()` from your own loop.

```python
from dune_fox import DuneFox

fox = DuneFox()
while True:
    if not fox.connected():
        continue
    pad = fox.poll()
    if pad is None:
        continue
    if pad.A:
        ...
    move_x, move_y = pad.lx, pad.ly
```

| Call | Use |
| --- | --- |
| `connected()` | True when a pad answers on slots 0–3. |
| `poll()` | Current buttons and sticks, or `None` if the pad is gone. |

Buttons on `Pad`: `A` `B` `X` `Y` `LB` `RB` `LS` `RS` `START` `BACK` `DPAD_U` `DPAD_D` `DPAD_L` `DPAD_R`. Sticks are `-1..1` (`lx` `ly` `rx` `ry`). Triggers are `0..1` (`lt` `rt`).

PC X-input: hold **FN + A** until the LED is yellow. Pairing pinhole on the FlySync receiver if it will not bind.

Host sketch: `examples/plug_play.py`.
