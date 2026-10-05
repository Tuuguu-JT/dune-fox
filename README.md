# dune-fox

A small library that reads a **FLYDIGI Dune Fox** on Windows or Linux. Your program calls `poll()` and uses the data it returns. The library does not run its own loop.

The pad must be in XInput mode: hold **FN + A** until the LED is yellow. Connect it with the FlySync dongle or a USB-C cable.

## Install

From this folder:

```bash
pip install -e .
```

Python 3.10 or newer. There are no extra packages. You can also copy `dune_fox.py` next to your program and import it from there.

## Use it in your loop

```python
from dune_fox import poll

while True:
    pad = poll()
    if pad is None:
        continue  # unplugged or asleep

    if pad.A:
        confirm()
    if pad.RT > 0.5:
        boost()

    drive(pad.lx, pad.ly)  # left stick, -1..1
```

`poll()` returns one fresh sample each time you call it, or `None` when no pad is connected. Read the fields on that object. A button is `True` for as long as it is held down.

`connected()` is only the connection check. It does not return the sticks or buttons.

```python
from dune_fox import connected

if connected():
    ...
```

See `examples/plug_play.py` for a loop that prints every field on one line:

```bash
python examples/plug_play.py
```

## What `poll()` gives you

| Field | Meaning |
| --- | --- |
| `A` `B` `X` `Y` | Face buttons |
| `LB` `RB` | Shoulders |
| `lt` `rt` | Triggers, `0` released to `1` fully pulled |
| `LS` `RS` | Stick clicks |
| `START` `BACK` | Menu buttons |
| `DPAD_U` `DPAD_D` `DPAD_L` `DPAD_R` | D-pad |
| `lx` `ly` | Left stick, `-1..1`. Right and up are positive |
| `rx` `ry` | Right stick, same range |

A resting stick reads as `0`, so a small amount of noise does not show up as movement.

## Linux

In XInput mode the dongle appears as an Xbox 360 pad. Your user needs to read `/dev/input`:

```bash
sudo usermod -aG input $USER
```

Log out and back in. If the receiver will not pair, use the pinhole on the FlySync dongle.
