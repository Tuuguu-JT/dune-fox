"""Poll a FLYDIGI Dune Fox from the caller's loop. Windows and Linux."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

_STICK_DEAD = 0.08
_TRIGGER_DEAD = 0.04

# Linux evdev codes. xpad (Xbox 360 / FlySync XInput) labels X and Y with the
# legacy BTN_X / BTN_Y numbers, which are swapped versus the compass spec.
_FACE_XBOX = {0x130: "A", 0x131: "B", 0x133: "X", 0x134: "Y"}
_FACE_SPEC = {0x130: "A", 0x131: "B", 0x134: "X", 0x133: "Y"}
_KEYS = {
    0x136: "LB",
    0x137: "RB",
    0x13A: "BACK",
    0x13B: "START",
    0x13D: "LS",
    0x13E: "RS",
    0x220: "DPAD_U",
    0x221: "DPAD_D",
    0x222: "DPAD_L",
    0x223: "DPAD_R",
}
_ABS_X, _ABS_Y, _ABS_Z = 0x00, 0x01, 0x02
_ABS_RX, _ABS_RY, _ABS_RZ = 0x03, 0x04, 0x05
_ABS_GAS, _ABS_BRAKE = 0x09, 0x0A
_ABS_HAT0X, _ABS_HAT0Y = 0x10, 0x11


@dataclass(frozen=True, slots=True)
class Pad:
    """One sample. Buttons are held-state. Sticks are -1..1 (up/right positive). Triggers are 0..1."""

    A: bool = False
    B: bool = False
    X: bool = False
    Y: bool = False
    START: bool = False
    BACK: bool = False
    LB: bool = False
    RB: bool = False
    LS: bool = False
    RS: bool = False
    DPAD_U: bool = False
    DPAD_D: bool = False
    DPAD_L: bool = False
    DPAD_R: bool = False
    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    lt: float = 0.0
    rt: float = 0.0

    def __str__(self) -> str:
        return (
            f"A:{int(self.A)} B:{int(self.B)} X:{int(self.X)} Y:{int(self.Y)} "
            f"LB:{int(self.LB)} RB:{int(self.RB)} LS:{int(self.LS)} RS:{int(self.RS)} "
            f"ST:{int(self.START)} BK:{int(self.BACK)} "
            f"U:{int(self.DPAD_U)} D:{int(self.DPAD_D)} L:{int(self.DPAD_L)} R:{int(self.DPAD_R)} "
            f"LX:{self.lx:+.2f} LY:{self.ly:+.2f} RX:{self.rx:+.2f} RY:{self.ry:+.2f} "
            f"LT:{self.lt:.2f} RT:{self.rt:.2f}"
        )


_WIDTH = len(str(Pad()))
_OFFLINE = "no FlySync pad".ljust(_WIDTH)
_dev: _Reader | None = None


class _Reader:
    def read(self) -> Pad | None:
        raise NotImplementedError


def poll() -> Pad | None:
    """Current buttons, sticks, and triggers. None when no pad is connected."""
    return _reader().read()


def connected() -> bool:
    """True when a pad is connected."""
    return poll() is not None


def line(pad: Pad | None) -> str:
    """Fixed-width status line. None becomes the disconnected message."""
    return _OFFLINE if pad is None else str(pad)


def main() -> None:
    """Print the pad on one updating line. Ctrl+C stops."""
    try:
        while True:
            try:
                text = line(poll())
            except PermissionError as exc:
                print(exc)
                return
            print(text, end="\r", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()


def _reader() -> _Reader:
    global _dev
    if _dev is None:
        if sys.platform == "win32":
            _dev = _XInput()
        elif sys.platform.startswith("linux"):
            _dev = _Evdev()
        else:
            raise OSError("dune_fox supports Windows and Linux")
    return _dev


def _clamp_stick(value: int, lo: int, hi: int, *, invert: bool = False) -> float:
    if hi == lo:
        return 0.0
    x = (value - lo) / (hi - lo) * 2.0 - 1.0
    if invert:
        x = -x
    x = max(-1.0, min(1.0, x))
    return 0.0 if abs(x) < _STICK_DEAD else x


def _clamp_trigger(value: int, lo: int, hi: int) -> float:
    if hi == lo:
        return 0.0
    x = (value - lo) / (hi - lo)
    x = max(0.0, min(1.0, x))
    return 0.0 if x < _TRIGGER_DEAD else x


def _pressed(bits: bytes, code: int) -> bool:
    byte = code // 8
    if byte >= len(bits):
        return False
    return bool(bits[byte] & (1 << (code % 8)))


class _XInput(_Reader):
    def __init__(self) -> None:
        self._dll = None
        self._slot: int | None = None

    def read(self) -> Pad | None:
        import ctypes
        from ctypes import wintypes as wt

        if self._dll is None:
            self._dll = _load_xinput(ctypes, wt)
            self._state_type = _xinput_state(ctypes, wt)
        if self._slot is not None:
            st = self._state(self._slot)
            if st is not None:
                return _pad_xinput(st)
        for i in range(4):
            if i == self._slot:
                continue
            st = self._state(i)
            if st is not None:
                self._slot = i
                return _pad_xinput(st)
        return None

    def _state(self, index: int):
        st = self._state_type()
        import ctypes

        if int(self._dll.XInputGetState(index, ctypes.byref(st))) != 0:
            return None
        return st


def _load_xinput(ctypes, wt):
    last: OSError | None = None
    for name in ("XInput1_4.dll", "XInput1_3.dll", "XInput9_1_0.dll"):
        try:
            dll = ctypes.WinDLL(name)
        except OSError as exc:
            last = exc
            continue
        dll.XInputGetState.argtypes = [wt.DWORD, ctypes.c_void_p]
        dll.XInputGetState.restype = wt.DWORD
        return dll
    raise OSError("XInput DLL not found") from last


def _xinput_state(ctypes, wt):
    class Gamepad(ctypes.Structure):
        _fields_ = [
            ("wButtons", wt.WORD),
            ("bLeftTrigger", wt.BYTE),
            ("bRightTrigger", wt.BYTE),
            ("sThumbLX", ctypes.c_short),
            ("sThumbLY", ctypes.c_short),
            ("sThumbRX", ctypes.c_short),
            ("sThumbRY", ctypes.c_short),
        ]

    class State(ctypes.Structure):
        _fields_ = [("dwPacketNumber", wt.DWORD), ("Gamepad", Gamepad)]

    return State


def _xinput_axis(v: int) -> float:
    x = max(-1.0, min(1.0, v / 32767.0 if v >= 0 else v / 32768.0))
    return 0.0 if abs(x) < _STICK_DEAD else x


def _xinput_trigger(v: int) -> float:
    x = max(0.0, min(1.0, v / 255.0))
    return 0.0 if x < _TRIGGER_DEAD else x


def _pad_xinput(st) -> Pad:
    g = st.Gamepad
    word = int(g.wButtons)
    masks = {
        "DPAD_U": 0x0001,
        "DPAD_D": 0x0002,
        "DPAD_L": 0x0004,
        "DPAD_R": 0x0008,
        "START": 0x0010,
        "BACK": 0x0020,
        "LS": 0x0040,
        "RS": 0x0080,
        "LB": 0x0100,
        "RB": 0x0200,
        "A": 0x1000,
        "B": 0x2000,
        "X": 0x4000,
        "Y": 0x8000,
    }
    flags = {name: bool(word & mask) for name, mask in masks.items()}
    return Pad(
        lx=_xinput_axis(g.sThumbLX),
        ly=_xinput_axis(g.sThumbLY),
        rx=_xinput_axis(g.sThumbRX),
        ry=_xinput_axis(g.sThumbRY),
        lt=_xinput_trigger(g.bLeftTrigger),
        rt=_xinput_trigger(g.bRightTrigger),
        **flags,
    )


class _Evdev(_Reader):
    def __init__(self) -> None:
        self._fd: int | None = None
        self._xbox = True
        self._ranges: dict[int, tuple[int, int]] = {}
        self._lt = _ABS_Z
        self._rt = _ABS_RZ
        self._has_hat = False
        self._retry = 0.0
        self._denied = False

    def read(self) -> Pad | None:
        if self._fd is None:
            now = time.perf_counter()
            if now < self._retry:
                if self._denied:
                    raise PermissionError(_PERMISSION)
                return None
            self._open()
            if self._fd is None:
                self._retry = now + 0.5
                if self._denied:
                    raise PermissionError(_PERMISSION)
                return None
        try:
            return self._sample()
        except OSError:
            self._close()
            return None

    def _open(self) -> None:
        import glob
        import os

        self._denied = False
        opened = False
        denied = False
        best: tuple[tuple[int, str], int, str] | None = None
        for path in glob.glob("/dev/input/event*"):
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
            except PermissionError:
                denied = True
                continue
            except OSError:
                continue
            opened = True
            try:
                if not _is_gamepad(fd):
                    os.close(fd)
                    continue
                name = _device_name(fd)
                rank = (_name_rank(name), path)
                if best is None or rank < best[0]:
                    if best is not None:
                        os.close(best[1])
                    best = (rank, fd, name)
                else:
                    os.close(fd)
            except OSError:
                os.close(fd)
        self._denied = denied and not opened
        if best is None:
            return
        self._fd = best[1]
        self._xbox = _xbox_name(best[2])
        self._prepare()

    def _prepare(self) -> None:
        assert self._fd is not None
        present = _abs_bits(self._fd)
        self._ranges = {}
        for code in (_ABS_X, _ABS_Y, _ABS_RX, _ABS_RY, _ABS_Z, _ABS_RZ, _ABS_GAS, _ABS_BRAKE, _ABS_HAT0X, _ABS_HAT0Y):
            if not _pressed(present, code):
                continue
            _value, lo, hi = _abs_info(self._fd, code)
            if hi != lo:
                self._ranges[code] = (lo, hi)
        self._lt = _ABS_Z if _ABS_Z in self._ranges else _ABS_BRAKE
        self._rt = _ABS_RZ if _ABS_RZ in self._ranges else _ABS_GAS
        self._has_hat = _ABS_HAT0X in self._ranges and _ABS_HAT0Y in self._ranges

    def _sample(self) -> Pad:
        assert self._fd is not None
        bits = _key_bits(self._fd)
        face = _FACE_XBOX if self._xbox else _FACE_SPEC
        flags = {name: False for name in (
            "A", "B", "X", "Y", "START", "BACK", "LB", "RB", "LS", "RS",
            "DPAD_U", "DPAD_D", "DPAD_L", "DPAD_R",
        )}
        for code, name in face.items():
            flags[name] = _pressed(bits, code)
        for code, name in _KEYS.items():
            if name.startswith("DPAD") and self._has_hat:
                continue
            flags[name] = _pressed(bits, code)
        if self._has_hat:
            hx = _abs_value(self._fd, _ABS_HAT0X)
            hy = _abs_value(self._fd, _ABS_HAT0Y)
            flags["DPAD_L"] = hx < 0
            flags["DPAD_R"] = hx > 0
            flags["DPAD_U"] = hy < 0
            flags["DPAD_D"] = hy > 0
        return Pad(
            lx=_axis(self._fd, _ABS_X, self._ranges),
            ly=_axis(self._fd, _ABS_Y, self._ranges, invert=True),
            rx=_axis(self._fd, _ABS_RX, self._ranges),
            ry=_axis(self._fd, _ABS_RY, self._ranges, invert=True),
            lt=_trig(self._fd, self._lt, self._ranges),
            rt=_trig(self._fd, self._rt, self._ranges),
            **flags,
        )

    def _close(self) -> None:
        import os

        if self._fd is not None:
            os.close(self._fd)
        self._fd = None


_PERMISSION = (
    "cannot read /dev/input. Add your user to the input group: "
    "sudo usermod -aG input $USER  (then log in again)"
)


def _ioc(direction: int, nr: int, size: int) -> int:
    value = (direction << 30) | (size << 16) | (ord("E") << 8) | nr
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def _ioctl(fd: int, nr: int, size: int) -> bytes:
    import fcntl

    buf = bytearray(size)
    fcntl.ioctl(fd, _ioc(2, nr, size), buf, True)
    return bytes(buf)


def _is_gamepad(fd: int) -> bool:
    # EV_KEY = 1. BTN_SOUTH = 0x130 sits inside a 96-byte key bitmap.
    bits = _ioctl(fd, 0x20 + 1, 96)
    return _pressed(bits, 0x130)


def _device_name(fd: int) -> str:
    raw = _ioctl(fd, 0x06, 256)
    return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")


def _key_bits(fd: int) -> bytes:
    return _ioctl(fd, 0x18, 96)


def _abs_bits(fd: int) -> bytes:
    # EV_ABS = 3.
    return _ioctl(fd, 0x20 + 3, 16)


def _abs_info(fd: int, code: int) -> tuple[int, int, int]:
    import struct

    raw = _ioctl(fd, 0x40 + code, 24)
    value, lo, hi, _fuzz, _flat, _resolution = struct.unpack("iiiiii", raw)
    return value, lo, hi


def _abs_value(fd: int, code: int) -> int:
    value, _lo, _hi = _abs_info(fd, code)
    return value


def _axis(fd: int, code: int, ranges: dict[int, tuple[int, int]], *, invert: bool = False) -> float:
    span = ranges.get(code)
    if span is None:
        return 0.0
    return _clamp_stick(_abs_value(fd, code), span[0], span[1], invert=invert)


def _trig(fd: int, code: int, ranges: dict[int, tuple[int, int]]) -> float:
    span = ranges.get(code)
    if span is None:
        return 0.0
    return _clamp_trigger(_abs_value(fd, code), span[0], span[1])


def _name_rank(name: str) -> int:
    text = name.lower()
    if "flydigi" in text or "dune" in text:
        return 0
    if _xbox_name(name):
        return 1
    if "gamepad" in text or "controller" in text:
        return 2
    return 3


def _xbox_name(name: str) -> bool:
    text = name.lower()
    return any(part in text for part in ("xbox", "x-box", "xinput", "360"))


if __name__ == "__main__":
    main()
