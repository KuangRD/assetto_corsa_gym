"""Consistent, read-only snapshots from RaceRoom's official ``$R3E`` map."""

import ctypes
import os
import struct
import time
from dataclasses import dataclass
from typing import Optional, Protocol

from assetto_corsa_gym.RacingEnv.errors import (
    AdapterConnectionError,
    InconsistentSnapshotError,
    PlatformNotSupportedError,
    SharedMemoryVersionError,
    TelemetryTimeoutError,
)

from .constants import API_VERSION_MAJOR, API_VERSION_MINOR, SHARED_MEMORY_NAME
from .structures import (
    PLAYER_TICK_OFFSET,
    SHARED_MEMORY_SIZE,
    R3EDriverData,
    R3EShared,
)


FILE_MAP_READ = 0x0004


class SnapshotSource(Protocol):
    """Byte source seam used by the Windows map and deterministic tests."""

    def open(self, size: int) -> None:
        ...

    def close(self) -> None:
        ...

    def read_int32(self, offset: int) -> int:
        ...

    def read_bytes(self, size: int) -> bytes:
        ...


class WindowsNamedSharedMemorySource:
    """Open an existing named map without accidentally creating a new one."""

    def __init__(self, name: str = SHARED_MEMORY_NAME):
        self.name = name
        self._kernel32 = None
        self._handle = None
        self._view = None

    def open(self, size: int) -> None:
        if os.name != "nt":
            raise PlatformNotSupportedError(
                "RaceRoom shared memory is available only on Windows"
            )

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenFileMappingW.argtypes = [
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.c_wchar_p,
        ]
        kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_size_t,
        ]
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

        handle = kernel32.OpenFileMappingW(FILE_MAP_READ, False, self.name)
        if not handle:
            error = ctypes.get_last_error()
            raise AdapterConnectionError(
                "RaceRoom shared memory {!r} is unavailable (WinError {}). "
                "Start an offline RaceRoom session and try again.".format(
                    self.name, error
                )
            )

        view = kernel32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, size)
        if not view:
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise AdapterConnectionError(
                "Could not map RaceRoom shared memory (WinError {})".format(error)
            )

        self._kernel32 = kernel32
        self._handle = handle
        self._view = view

    def close(self) -> None:
        if self._kernel32 is not None and self._view:
            self._kernel32.UnmapViewOfFile(self._view)
        if self._kernel32 is not None and self._handle:
            self._kernel32.CloseHandle(self._handle)
        self._view = None
        self._handle = None
        self._kernel32 = None

    def _address(self) -> int:
        if not self._view:
            raise AdapterConnectionError("RaceRoom shared memory is not open")
        return int(self._view)

    def read_int32(self, offset: int) -> int:
        return ctypes.c_int32.from_address(self._address() + offset).value

    def read_bytes(self, size: int) -> bytes:
        return ctypes.string_at(self._address(), size)


@dataclass(frozen=True)
class SharedMemorySnapshot:
    data: R3EShared
    payload: bytes
    received_at_s: float
    sequence_reset: bool = False

    @property
    def sequence(self) -> int:
        return int(self.data.player.game_simulation_ticks)


@dataclass
class SnapshotReaderStats:
    snapshots: int = 0
    torn_read_retries: int = 0
    duplicate_sequences: int = 0
    sequence_resets: int = 0


class RaceRoomSharedMemory:
    """Lifecycle, ABI validation, deduplication, and stable snapshot reads."""

    def __init__(
        self,
        name: str = SHARED_MEMORY_NAME,
        expected_major: int = API_VERSION_MAJOR,
        minimum_minor: int = API_VERSION_MINOR,
        strict_minor: bool = False,
        max_snapshot_attempts: int = 8,
        poll_interval_s: float = 0.001,
        source: Optional[SnapshotSource] = None,
    ):
        self.name = name
        self.expected_major = expected_major
        self.minimum_minor = minimum_minor
        self.strict_minor = strict_minor
        self.max_snapshot_attempts = max_snapshot_attempts
        self.poll_interval_s = poll_interval_s
        self.source = source or WindowsNamedSharedMemorySource(name)
        self.stats = SnapshotReaderStats()
        self.connected = False

    def open(self) -> SharedMemorySnapshot:
        if self.connected:
            return self.read_consistent_snapshot()
        self.source.open(SHARED_MEMORY_SIZE)
        self.connected = True
        try:
            snapshot = self.read_consistent_snapshot()
            self._validate_layout(snapshot.data)
            return snapshot
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        try:
            self.source.close()
        finally:
            self.connected = False

    def __enter__(self) -> "RaceRoomSharedMemory":
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _require_open(self) -> None:
        if not self.connected:
            raise AdapterConnectionError("RaceRoom shared memory is not open")

    def _validate_layout(self, data: R3EShared) -> None:
        major = int(data.version_major)
        minor = int(data.version_minor)
        if major != self.expected_major:
            raise SharedMemoryVersionError(
                "RaceRoom API major {} is incompatible with expected {}".format(
                    major, self.expected_major
                )
            )
        if self.strict_minor and minor != self.minimum_minor:
            raise SharedMemoryVersionError(
                "RaceRoom API minor {} does not equal required {}".format(
                    minor, self.minimum_minor
                )
            )
        if minor < self.minimum_minor:
            raise SharedMemoryVersionError(
                "RaceRoom API {}.{} is older than supported {}.{}".format(
                    major, minor, self.expected_major, self.minimum_minor
                )
            )

        expected_driver_offset = R3EShared.num_cars.offset
        expected_driver_size = ctypes.sizeof(R3EDriverData)
        if int(data.all_drivers_offset) != expected_driver_offset:
            raise SharedMemoryVersionError(
                "all_drivers_offset {} does not match ctypes offset {}".format(
                    int(data.all_drivers_offset), expected_driver_offset
                )
            )
        if int(data.driver_data_size) != expected_driver_size:
            raise SharedMemoryVersionError(
                "driver_data_size {} does not match ctypes size {}".format(
                    int(data.driver_data_size), expected_driver_size
                )
            )

    def read_consistent_snapshot(self) -> SharedMemorySnapshot:
        self._require_open()
        for _ in range(self.max_snapshot_attempts):
            tick_before = self.source.read_int32(PLAYER_TICK_OFFSET)
            payload = self.source.read_bytes(SHARED_MEMORY_SIZE)
            tick_after = self.source.read_int32(PLAYER_TICK_OFFSET)
            payload_tick = struct.unpack_from("<i", payload, PLAYER_TICK_OFFSET)[0]
            if tick_before == payload_tick == tick_after:
                data = R3EShared.from_buffer_copy(payload)
                self._validate_layout(data)
                self.stats.snapshots += 1
                return SharedMemorySnapshot(
                    data=data,
                    payload=payload,
                    received_at_s=time.perf_counter(),
                )
            self.stats.torn_read_retries += 1

        raise InconsistentSnapshotError(
            "RaceRoom shared memory changed during {} consecutive reads".format(
                self.max_snapshot_attempts
            )
        )

    def wait_for_snapshot(
        self, after_sequence: int, timeout_s: float
    ) -> SharedMemorySnapshot:
        """Wait for a new tick; a backward tick is returned as a session reset."""

        deadline = time.perf_counter() + timeout_s
        while True:
            snapshot = self.read_consistent_snapshot()
            sequence = snapshot.sequence
            if sequence > after_sequence:
                return snapshot
            if sequence < after_sequence:
                self.stats.sequence_resets += 1
                return SharedMemorySnapshot(
                    data=snapshot.data,
                    payload=snapshot.payload,
                    received_at_s=snapshot.received_at_s,
                    sequence_reset=True,
                )

            self.stats.duplicate_sequences += 1
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TelemetryTimeoutError(
                    "No RaceRoom tick newer than {} within {:.3f}s".format(
                        after_sequence, timeout_s
                    )
                )
            time.sleep(min(self.poll_interval_s, remaining))
