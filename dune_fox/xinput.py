"""Windows XInput backend for the FlySync dongle (Xbox 360 identity)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

XINPUT_DLLS = ("XInput1_4.dll", "XInput1_3.dll", "XInput9_1_0.dll")
ERROR_DEVICE_NOT_CONNECTED = 1167

XINPUT_GAMEPAD_DPAD_UP = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT = 0x0008
XINPUT_GAMEPAD_START = 0x0010
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_GAMEPAD_LEFT_THUMB = 0x0040
XINPUT_GAMEPAD_RIGHT_THUMB = 0x0080
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
XINPUT_GAMEPAD_A = 0x1000
XINPUT_GAMEPAD_B = 0x2000
XINPUT_GAMEPAD_X = 0x4000
XINPUT_GAMEPAD_Y = 0x8000

BUTTON_MAP = (
    ("DPAD_U", XINPUT_GAMEPAD_DPAD_UP),
    ("DPAD_D", XINPUT_GAMEPAD_DPAD_DOWN),
    ("DPAD_L", XINPUT_GAMEPAD_DPAD_LEFT),
    ("DPAD_R", XINPUT_GAMEPAD_DPAD_RIGHT),
    ("START", XINPUT_GAMEPAD_START),
    ("BACK", XINPUT_GAMEPAD_BACK),
    ("LS", XINPUT_GAMEPAD_LEFT_THUMB),
    ("RS", XINPUT_GAMEPAD_RIGHT_THUMB),
    ("LB", XINPUT_GAMEPAD_LEFT_SHOULDER),
    ("RB", XINPUT_GAMEPAD_RIGHT_SHOULDER),
    ("A", XINPUT_GAMEPAD_A),
    ("B", XINPUT_GAMEPAD_B),
    ("X", XINPUT_GAMEPAD_X),
    ("Y", XINPUT_GAMEPAD_Y),
)

BATTERY_TYPE = {0: "disconnected", 1: "wired", 2: "alkaline", 3: "nimh", 0xFF: "unknown"}
BATTERY_LEVEL = {0: "empty", 1: "low", 2: "medium", 3: "full"}
BATTERY_FRAC = {0: 0.0, 1: 0.25, 2: 0.6, 3: 1.0}


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wt.WORD),
        ("bLeftTrigger", wt.BYTE),
        ("bRightTrigger", wt.BYTE),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wt.DWORD),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


class XINPUT_BATTERY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BatteryType", wt.BYTE),
        ("BatteryLevel", wt.BYTE),
    ]


def load_dll() -> ctypes.WinDLL:
    last: OSError | None = None
    for name in XINPUT_DLLS:
        try:
            dll = ctypes.WinDLL(name)
            dll.XInputGetState.argtypes = [wt.DWORD, ctypes.POINTER(XINPUT_STATE)]
            dll.XInputGetState.restype = wt.DWORD
            return dll
        except OSError as exc:
            last = exc
    raise OSError(f"XInput DLL not found ({', '.join(XINPUT_DLLS)})") from last


def get_state(dll: ctypes.WinDLL, index: int) -> tuple[int, XINPUT_STATE | None]:
    st = XINPUT_STATE()
    err = int(dll.XInputGetState(index, ctypes.byref(st)))
    if err != 0:
        return err, None
    return 0, st


def first_slot(dll: ctypes.WinDLL, preferred: int | None = None) -> int | None:
    order = list(range(4))
    if preferred in order:
        order.remove(preferred)
        order.insert(0, preferred)
    for i in order:
        err, _ = get_state(dll, i)
        if err == 0:
            return i
    return None


def battery(dll: ctypes.WinDLL, index: int) -> tuple[str, str, float]:
    try:
        dll.XInputGetBatteryInformation.argtypes = [
            wt.DWORD,
            wt.BYTE,
            ctypes.POINTER(XINPUT_BATTERY_INFORMATION),
        ]
        dll.XInputGetBatteryInformation.restype = wt.DWORD
    except AttributeError:
        return "unknown", "unknown", -1.0
    info = XINPUT_BATTERY_INFORMATION()
    if dll.XInputGetBatteryInformation(index, 0, ctypes.byref(info)) != 0:
        return "unknown", "unknown", -1.0
    kind = BATTERY_TYPE.get(info.BatteryType, str(info.BatteryType))
    level = BATTERY_LEVEL.get(info.BatteryLevel, str(info.BatteryLevel))
    frac = BATTERY_FRAC.get(info.BatteryLevel, -1.0)
    if info.BatteryType == 0:
        frac = 0.0
    if info.BatteryType == 1:
        frac = 1.0
    return kind, level, frac


def norm_axis(v: int, dead: float) -> float:
    x = max(-1.0, min(1.0, v / 32767.0 if v >= 0 else v / 32768.0))
    return 0.0 if abs(x) < dead else x


def norm_trigger(v: int, dead: float) -> float:
    x = max(0.0, min(1.0, v / 255.0))
    return 0.0 if x < dead else x


def buttons_from(word: int) -> dict[str, bool]:
    return {name: bool(word & mask) for name, mask in BUTTON_MAP}
