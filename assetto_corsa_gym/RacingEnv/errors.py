"""Errors shared by simulator adapters."""


class SimulatorError(RuntimeError):
    """Base class for simulator integration failures."""


class AdapterConnectionError(SimulatorError):
    """The simulator data source could not be opened."""


class PlatformNotSupportedError(AdapterConnectionError):
    """The adapter is unavailable on the current operating system."""


class SharedMemoryVersionError(AdapterConnectionError):
    """The mapped API version or layout is incompatible."""


class InconsistentSnapshotError(SimulatorError):
    """A stable shared-memory snapshot could not be obtained."""


class TelemetryTimeoutError(SimulatorError):
    """No qualifying new telemetry frame arrived before the deadline."""


class UnsafeSessionError(SimulatorError):
    """Automated control was requested in a forbidden session."""
