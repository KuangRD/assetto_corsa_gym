"""Small, dependency-free wrapper around the official vJoy interface DLL."""

import ctypes
import os
from enum import IntEnum
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

from ..errors import AdapterConnectionError, PlatformNotSupportedError


DEFAULT_VJOY_DLL = Path(r"C:\Program Files\vJoy\x64\vJoyInterface.dll")


class VJoyStatus(IntEnum):
    OWN = 0
    FREE = 1
    BUSY = 2
    MISSING = 3
    UNKNOWN = 4


HID_USAGE: Dict[str, int] = {
    "x": 0x30,
    "y": 0x31,
    "z": 0x32,
    "rx": 0x33,
    "ry": 0x34,
    "rz": 0x35,
    "slider0": 0x36,
    "slider1": 0x37,
}


def scale_percent(percent: float, minimum: int, maximum: int) -> int:
    """Convert a 0..100 percentage to an inclusive vJoy axis range."""

    value = float(percent)
    if not 0.0 <= value <= 100.0:
        raise ValueError("vJoy axis percentage must be between 0 and 100")
    return int(round(minimum + (maximum - minimum) * value / 100.0))


class WindowsVJoyDevice:
    """Own one vJoy device and write axes/buttons through the normal SDK API."""

    def __init__(
        self,
        device_id: int = 1,
        dll_path: Optional[Union[os.PathLike, str]] = None,
    ) -> None:
        if os.name != "nt":
            raise PlatformNotSupportedError("vJoy control requires Windows")
        if not 1 <= int(device_id) <= 16:
            raise ValueError("vJoy device_id must be between 1 and 16")

        self.device_id = int(device_id)
        self.dll_path = Path(dll_path or DEFAULT_VJOY_DLL)
        if not self.dll_path.is_file():
            raise AdapterConnectionError(
                "vJoy interface DLL was not found at {}".format(self.dll_path)
            )

        self._dll = ctypes.CDLL(str(self.dll_path))
        self._owned = False
        self._configure_api()

    def _configure_api(self) -> None:
        self._dll.vJoyEnabled.argtypes = []
        self._dll.vJoyEnabled.restype = ctypes.c_bool
        self._dll.GetvJoyVersion.argtypes = []
        self._dll.GetvJoyVersion.restype = ctypes.c_short
        self._dll.GetVJDStatus.argtypes = [ctypes.c_uint]
        self._dll.GetVJDStatus.restype = ctypes.c_int
        self._dll.AcquireVJD.argtypes = [ctypes.c_uint]
        self._dll.AcquireVJD.restype = ctypes.c_bool
        self._dll.RelinquishVJD.argtypes = [ctypes.c_uint]
        self._dll.RelinquishVJD.restype = None
        self._dll.GetVJDAxisExist.argtypes = [ctypes.c_uint, ctypes.c_uint]
        self._dll.GetVJDAxisExist.restype = ctypes.c_bool
        self._dll.GetVJDAxisMin.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_long),
        ]
        self._dll.GetVJDAxisMin.restype = ctypes.c_bool
        self._dll.GetVJDAxisMax.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_long),
        ]
        self._dll.GetVJDAxisMax.restype = ctypes.c_bool
        self._dll.SetAxis.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_uint]
        self._dll.SetAxis.restype = ctypes.c_bool
        self._dll.SetBtn.argtypes = [ctypes.c_bool, ctypes.c_uint, ctypes.c_ubyte]
        self._dll.SetBtn.restype = ctypes.c_bool

    @property
    def version(self) -> int:
        return int(self._dll.GetvJoyVersion()) & 0xFFFF

    @property
    def status(self) -> VJoyStatus:
        try:
            return VJoyStatus(int(self._dll.GetVJDStatus(self.device_id)))
        except ValueError:
            return VJoyStatus.UNKNOWN

    @property
    def owned(self) -> bool:
        return self._owned or self.status == VJoyStatus.OWN

    def assert_enabled(self) -> None:
        if not self._dll.vJoyEnabled():
            raise AdapterConnectionError("The vJoy driver is installed but disabled")
        status = self.status
        if status == VJoyStatus.MISSING:
            raise AdapterConnectionError(
                "vJoy Device {} is not configured".format(self.device_id)
            )
        if status == VJoyStatus.UNKNOWN:
            raise AdapterConnectionError(
                "vJoy Device {} returned an unknown status".format(self.device_id)
            )

    def acquire(self) -> None:
        self.assert_enabled()
        status = self.status
        if status == VJoyStatus.BUSY:
            raise AdapterConnectionError(
                "vJoy Device {} is owned by another feeder; close vJoyFeeder first".format(
                    self.device_id
                )
            )
        if status == VJoyStatus.OWN:
            self._owned = True
            return
        if status != VJoyStatus.FREE or not self._dll.AcquireVJD(self.device_id):
            raise AdapterConnectionError(
                "Could not acquire vJoy Device {}".format(self.device_id)
            )
        self._owned = True

    def axis_bounds(self, axis: str) -> Tuple[int, int]:
        usage = self._axis_usage(axis)
        minimum = ctypes.c_long()
        maximum = ctypes.c_long()
        if not self._dll.GetVJDAxisMin(
            self.device_id, usage, ctypes.byref(minimum)
        ) or not self._dll.GetVJDAxisMax(
            self.device_id, usage, ctypes.byref(maximum)
        ):
            raise AdapterConnectionError(
                "Could not read vJoy {} axis bounds".format(axis.upper())
            )
        return int(minimum.value), int(maximum.value)

    def set_axis_percent(self, axis: str, percent: float) -> None:
        self._require_owned()
        usage = self._axis_usage(axis)
        minimum, maximum = self.axis_bounds(axis)
        raw = scale_percent(percent, minimum, maximum)
        if not self._dll.SetAxis(raw, self.device_id, usage):
            raise AdapterConnectionError(
                "vJoy rejected {} axis value {}".format(axis.upper(), raw)
            )

    def set_button(self, button: int, pressed: bool) -> None:
        self._require_owned()
        if not 1 <= int(button) <= 128:
            raise ValueError("vJoy button must be between 1 and 128")
        if not self._dll.SetBtn(bool(pressed), self.device_id, int(button)):
            raise AdapterConnectionError(
                "vJoy rejected button {} state".format(button)
            )

    def close(self) -> None:
        if self._owned:
            self._dll.RelinquishVJD(self.device_id)
            self._owned = False

    def _axis_usage(self, axis: str) -> int:
        key = axis.lower()
        if key not in HID_USAGE:
            raise ValueError("Unknown vJoy axis {!r}".format(axis))
        usage = HID_USAGE[key]
        if not self._dll.GetVJDAxisExist(self.device_id, usage):
            raise AdapterConnectionError(
                "vJoy Device {} has no {} axis".format(
                    self.device_id, key.upper()
                )
            )
        return usage

    def _require_owned(self) -> None:
        if not self.owned:
            raise AdapterConnectionError(
                "vJoy Device {} has not been acquired".format(self.device_id)
            )

    def __enter__(self) -> "WindowsVJoyDevice":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
