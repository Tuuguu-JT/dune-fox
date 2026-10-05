"""Poll a FLYDIGI Dune Fox. Windows (XInput) and Linux (evdev)."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

_STICK_DEAD = 0.08
_TRIGGER_DEAD = 0.04

# xpad reports the X/Y buttons on the legacy BTN_X / BTN_Y codes.
_FACE_XBOX = {0x130: "A", 0x131: "B", 0x133: "X", 0x134: "Y"}
_FACE_SPEC = {0x130: "A", 0x131: "B", 0x134: "X", 0x133: "Y"}
_KEYS = {
    0x136: "LB", 0x137: "RB", 0x13A: "BACK", 0x13B: "START",
    0x13D: "LS", 0x13E: "RS",
    0x220: "DPAD_U", 0x221: "DPAD_D", 0x222: "DPAD_L", 0x223: "DPAD_R",
}
_XINPUT_BITS = (
    ("DPAD_U", 0x0001), ("DPAD_D", 0x0002), ("DPAD_L", 0x0004), ("DPAD_R", 0x0008),
    ("START", 0x0010), ("BACK", 0x0020), ("LS", 0x0040), ("RS", 0x0080),
    ("LB", 0x0100), ("RB", 0x0200), ("A", 0x1000), ("B", 0x2000),
    ("X", 0x4000), ("Y", 0x8000),
)
_ABS = {
    "lx": 0x00, "ly": 0x01, "rx": 0x03, "ry": 0x04,
    "lz": 0x02, "rz": 0x05, "gas": 0x09, "brake": 0x0A,
    "hx": 0x10, "hy": 0x11,
}
_PERMISSION = (
    "cannot read /dev/input. Add your user to the input group: "
    "sudo usermod -aG input $USER  (then log in again)"
)
_dev = None


@dataclass(frozen=True, slots=True)
class Pad:
    """Latest sample. Buttons are held. Sticks are -1..1 (up/right positive). Triggers are 0..1."""

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


def poll() -> Pad | None:
    """Current pad data, or None when nothing is connected."""
    global _dev
    if _dev is None:
        if sys.platform == "win32":
            _dev = _XInput()
        elif sys.platform.startswith("linux"):
            _dev = _Evdev()
        else:
            raise OSError("dune_fox supports Windows and Linux")
    return _dev.read()


def connected() -> bool:
    """True when a pad is connected."""
    return poll() is not None


def _dead_stick(x: float) -> float:
    x = max(-1.0, min(1.0, x))
    return 0.0 if abs(x) < _STICK_DEAD else x


def _dead_trigger(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 0.0 if x < _TRIGGER_DEAD else x


def _bit(buf: bytes, code: int) -> bool:
    i = code // 8
    return i < len(buf) and bool(buf[i] & (1 << (code % 8)))


class _XInput:
    def __init__(self) -> None:
        self._dll = None
        self._state = None
        self._slot: int | None = None

    def read(self) -> Pad | None:
        import ctypes
        from ctypes import wintypes as wt

        if self._dll is None:
            self._dll, self._state = _load_xinput(ctypes, wt)
        for slot in ((self._slot,) if self._slot is not None else ()) + tuple(
            i for i in range(4) if i != self._slot
        ):
            st = self._state()
            if int(self._dll.XInputGetState(slot, ctypes.byref(st))) != 0:
                continue
            self._slot = slot
            g = st.Gamepad
            word = int(g.wButtons)
            return Pad(
                lx=_dead_stick(g.sThumbLX / (32767.0 if g.sThumbLX >= 0 else 32768.0)),
                ly=_dead_stick(g.sThumbLY / (32767.0 if g.sThumbLY >= 0 else 32768.0)),
                rx=_dead_stick(g.sThumbRX / (32767.0 if g.sThumbRX >= 0 else 32768.0)),
                ry=_dead_stick(g.sThumbRY / (32767.0 if g.sThumbRY >= 0 else 32768.0)),
                lt=_dead_trigger(g.bLeftTrigger / 255.0),
                rt=_dead_trigger(g.bRightTrigger / 255.0),
                **{name: bool(word & mask) for name, mask in _XINPUT_BITS},
            )
        return None


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

        return dll, State
    raise OSError("XInput DLL not found") from last


class _Evdev:
    def __init__(self) -> None:
        self._fd: int | None = None
        self._xbox = True
        self._range: dict[int, tuple[int, int]] = {}
        self._lt = _ABS["lz"]
        self._rt = _ABS["rz"]
        self._hat = False
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

        opened = denied = False
        best = None
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
                if not _bit(_ioctl(fd, 0x21, 96), 0x130):
                    os.close(fd)
                    continue
                name = _ioctl(fd, 0x06, 256).split(b"\x00", 1)[0].decode("utf-8", "replace")
                rank = (_rank(name), path)
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
        self._fd, name = best[1], best[2]
        text = name.lower()
        self._xbox = any(part in text for part in ("xbox", "x-box", "xinput", "360"))
        present = _ioctl(self._fd, 0x23, 16)
        self._range = {}
        for code in _ABS.values():
            if not _bit(present, code):
                continue
            _value, lo, hi = _abs(self._fd, code)
            if hi != lo:
                self._range[code] = (lo, hi)
        self._lt = _ABS["lz"] if _ABS["lz"] in self._range else _ABS["brake"]
        self._rt = _ABS["rz"] if _ABS["rz"] in self._range else _ABS["gas"]
        self._hat = _ABS["hx"] in self._range and _ABS["hy"] in self._range

    def _sample(self) -> Pad:
        assert self._fd is not None
        bits = _ioctl(self._fd, 0x18, 96)
        flags = dict.fromkeys(
            ("A", "B", "X", "Y", "START", "BACK", "LB", "RB", "LS", "RS",
             "DPAD_U", "DPAD_D", "DPAD_L", "DPAD_R"),
            False,
        )
        for code, name in (_FACE_XBOX if self._xbox else _FACE_SPEC).items():
            flags[name] = _bit(bits, code)
        for code, name in _KEYS.items():
            if not (name.startswith("DPAD") and self._hat):
                flags[name] = _bit(bits, code)
        if self._hat:
            hx, hy = _abs(self._fd, _ABS["hx"])[0], _abs(self._fd, _ABS["hy"])[0]
            flags["DPAD_L"], flags["DPAD_R"] = hx < 0, hx > 0
            flags["DPAD_U"], flags["DPAD_D"] = hy < 0, hy > 0
        return Pad(
            lx=self._stick("lx"),
            ly=self._stick("ly", invert=True),
            rx=self._stick("rx"),
            ry=self._stick("ry", invert=True),
            lt=self._trigger(self._lt),
            rt=self._trigger(self._rt),
            **flags,
        )

    def _stick(self, name: str, invert: bool = False) -> float:
        span = self._range.get(_ABS[name])
        if span is None or self._fd is None:
            return 0.0
        value, lo, hi = _abs(self._fd, _ABS[name])
        lo, hi = span
        x = (value - lo) / (hi - lo) * 2.0 - 1.0
        return _dead_stick(-x if invert else x)

    def _trigger(self, code: int) -> float:
        span = self._range.get(code)
        if span is None or self._fd is None:
            return 0.0
        value = _abs(self._fd, code)[0]
        lo, hi = span
        return _dead_trigger((value - lo) / (hi - lo))

    def _close(self) -> None:
        import os

        if self._fd is not None:
            os.close(self._fd)
        self._fd = None


def _ioctl(fd: int, nr: int, size: int) -> bytes:
    import fcntl

    value = (2 << 30) | (size << 16) | (ord("E") << 8) | nr
    if value >= 0x80000000:
        value -= 0x100000000
    buf = bytearray(size)
    fcntl.ioctl(fd, value, buf, True)
    return bytes(buf)


def _abs(fd: int, code: int) -> tuple[int, int, int]:
    import struct

    value, lo, hi, _fuzz, _flat, _res = struct.unpack("iiiiii", _ioctl(fd, 0x40 + code, 24))
    return value, lo, hi


def _rank(name: str) -> int:
    text = name.lower()
    if "flydigi" in text or "dune" in text:
        return 0
    if any(part in text for part in ("xbox", "x-box", "xinput", "360")):
        return 1
    if "gamepad" in text or "controller" in text:
        return 2
    return 3
