"""Versioned, simulator-neutral data contracts.

The contracts intentionally avoid exposing simulator-specific raw structures to
environment and learning code.  Tuples are used for vectors so frozen frames do
not contain mutable numpy arrays.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple


Vector3 = Tuple[float, float, float]


@dataclass(frozen=True)
class DriverAction:
    """Normalized driver command used by all new adapters."""

    steering: float
    throttle: float
    brake: float
    clutch: Optional[float] = None
    shift_up: bool = False
    shift_down: bool = False


@dataclass(frozen=True)
class AppliedAction:
    """Action values actually accepted by a control backend."""

    action: DriverAction
    applied_at_s: float
    limited: bool = False


@dataclass(frozen=True)
class StaticSessionInfo:
    simulator: str
    adapter_version: str
    api_version: str
    game_mode: int
    session_type: int
    control_type: int
    track_id: Optional[int] = None
    layout_id: Optional[int] = None
    car_id: Optional[int] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterHealth:
    connected: bool
    controls_enabled: bool
    last_sequence: Optional[int]
    telemetry_age_s: Optional[float]
    detail: str = ""


@dataclass(frozen=True)
class TelemetryFrame:
    """Canonical telemetry frame emitted by simulator adapters.

    Optional vectors remain unavailable until the adapter can establish a
    trustworthy axis mapping.  Missing API values are represented by ``None``
    and listed in ``availability``; they are never silently replaced with zero.
    """

    schema_version: str
    simulator: str
    sequence: int
    simulation_time_s: float
    received_at_s: float

    speed_mps: Optional[float]
    rpm: Optional[float]
    gear: Optional[int]

    position_xyz_m: Optional[Vector3]
    orientation_rpy_rad: Optional[Vector3]
    local_velocity_xyz_mps: Optional[Vector3]
    local_acceleration_xyz_mps2: Optional[Vector3]
    local_angular_velocity_xyz_radps: Optional[Vector3]

    steering_normalized: Optional[float]
    throttle_normalized: Optional[float]
    brake_normalized: Optional[float]
    ffb_normalized: Optional[float]

    lap_fraction: Optional[float]
    completed_laps: int
    lap_valid: Optional[bool]
    in_pitlane: Optional[bool]
    game_mode: int
    session_type: int
    session_phase: int
    control_type: int

    availability: Mapping[str, bool] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)
