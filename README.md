# dune-fox

Poll a **FLYDIGI Dune Fox** on Windows or Linux. Use the FlySync dongle or USB-C in XInput mode (hold **FN + A** until the LED is yellow).

```python
from dune_fox import poll

pad = poll()          # None when the pad is unplugged
if pad is None:
    ...
elif pad.A:
    move_x, move_y = pad.lx, pad.ly
```

| Call | Returns |
| --- | --- |
| `poll()` | A `Pad` you can read, or `None` if the pad is gone. |
| `connected()` | True when a pad is connected. |

Example loop: `examples/plug_play.py`.

Buttons: `A` `B` `X` `Y` `LB` `RB` `LS` `RS` `START` `BACK` `DPAD_U` `DPAD_D` `DPAD_L` `DPAD_R`. Sticks `lx` `ly` `rx` `ry` are `-1..1` with up and right positive. Triggers `lt` `rt` are `0..1`.

On Linux the dongle is an Xbox 360 pad. Your user needs access to `/dev/input`:

```bash
sudo usermod -aG input $USER
```

Log out and back in after that. Pairing pinhole on the FlySync receiver if it will not bind.
