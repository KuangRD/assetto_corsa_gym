"""Minimal Windows SendInput backend for normal in-game key bindings."""

import ctypes
import os
from ctypes import wintypes
from typing import Dict, Iterable

from ..errors import AdapterConnectionError, PlatformNotSupportedError


INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

VIRTUAL_KEYS: Dict[str, int] = {
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "q": 0x51,
    "z": 0x5A,
}

SCAN_CODES: Dict[str, tuple[int, bool]] = {
    "up": (0x48, True),
    "down": (0x50, True),
    "left": (0x4B, True),
    "right": (0x4D, True),
    "q": (0x10, False),
    "z": (0x2C, False),
}


ULONG_PTR = wintypes.WPARAM


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", INPUT_UNION)]


class WindowsKeyboardBackend:
    """Send keys only while the explicitly expected game PID has focus."""

    def __init__(self, expected_foreground_pid: int):
        if os.name != "nt":
            raise PlatformNotSupportedError("Keyboard control requires Windows")
        self.expected_foreground_pid = expected_foreground_pid
        self._pressed = set()
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(INPUT),
            ctypes.c_int,
        ]
        self._user32.SendInput.restype = wintypes.UINT
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]

    def foreground_pid(self) -> int:
        window = self._user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        return int(pid.value)

    def assert_game_has_focus(self) -> None:
        actual = self.foreground_pid()
        if actual != self.expected_foreground_pid:
            raise AdapterConnectionError(
                "Keyboard control refused: foreground PID {} is not RaceRoom PID {}".format(
                    actual, self.expected_foreground_pid
                )
            )

    def _send(self, key: str, key_up: bool) -> None:
        if key not in SCAN_CODES:
            raise ValueError("Unsupported key {!r}".format(key))
        self.assert_game_has_focus()
        scan_code, extended = SCAN_CODES[key]
        flags = KEYEVENTF_SCANCODE
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        if key_up:
            flags |= KEYEVENTF_KEYUP
        event = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(
                wVk=0,
                wScan=scan_code,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )
        sent = self._user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent != 1:
            raise AdapterConnectionError(
                "SendInput failed for {} (WinError {})".format(
                    key, ctypes.get_last_error()
                )
            )

    def key_down(self, key: str) -> None:
        if key not in self._pressed:
            self._send(key, key_up=False)
            self._pressed.add(key)

    def key_up(self, key: str) -> None:
        if key in self._pressed:
            self._send(key, key_up=True)
            self._pressed.discard(key)

    def release_all(self, keys: Iterable[str] = VIRTUAL_KEYS) -> None:
        """Best-effort release; it is safe to send key-up for untracked keys."""

        for key in keys:
            try:
                scan_code, extended = SCAN_CODES[key]
                flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
                if extended:
                    flags |= KEYEVENTF_EXTENDEDKEY
                event = INPUT(
                    type=INPUT_KEYBOARD,
                    ki=KEYBDINPUT(
                        wVk=0,
                        wScan=scan_code,
                        dwFlags=flags,
                        time=0,
                        dwExtraInfo=0,
                    ),
                )
                self._user32.SendInput(
                    1, ctypes.byref(event), ctypes.sizeof(INPUT)
                )
            except Exception:
                pass
        self._pressed.clear()
