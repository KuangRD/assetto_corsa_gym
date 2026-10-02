"""Protocol implemented by simulator integrations."""

from typing import Any, Protocol

from ..types import (
    AdapterHealth,
    AppliedAction,
    DriverAction,
    StaticSessionInfo,
    TelemetryFrame,
)


class SimulatorAdapter(Protocol):
    def connect(self) -> StaticSessionInfo:
        ...

    def close(self) -> None:
        ...

    def wait_for_frame(
        self, after_sequence: int, timeout_s: float
    ) -> TelemetryFrame:
        ...

    def apply_action(self, action: DriverAction) -> AppliedAction:
        ...

    def reset(self, request: Any) -> Any:
        ...

    def emergency_stop(self, reason: str) -> None:
        ...

    def health(self) -> AdapterHealth:
        ...
