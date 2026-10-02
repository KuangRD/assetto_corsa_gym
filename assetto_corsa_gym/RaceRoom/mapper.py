"""Map packed RaceRoom data into versioned neutral telemetry frames."""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from assetto_corsa_gym.RacingEnv.types import TelemetryFrame, Vector3

from .shared_memory import SharedMemorySnapshot
from .structures import Vec3F64, decode_u8_string
from .version import TELEMETRY_SCHEMA_VERSION


@dataclass(frozen=True)
class AxisTransform:
    """Explicit mapping from RaceRoom local axes to neutral x/y/z axes."""

    indices: Tuple[int, int, int]
    signs: Tuple[float, float, float]
    validation_id: str

    def apply(self, value: Vec3F64) -> Vector3:
        source = (float(value.x), float(value.y), float(value.z))
        return tuple(
            source[index] * sign
            for index, sign in zip(self.indices, self.signs)
        )  # type: ignore[return-value]


def _finite(value: float) -> bool:
    return math.isfinite(float(value))


def _optional_nonnegative(value: float) -> Optional[float]:
    value = float(value)
    return value if _finite(value) and value >= 0.0 else None


def _optional_flag(value: int) -> Optional[bool]:
    if value == 0:
        return False
    if value == 1:
        return True
    return None


def _vec3(value: Vec3F64) -> Optional[Vector3]:
    result = (float(value.x), float(value.y), float(value.z))
    return result if all(_finite(component) for component in result) else None


class RaceRoomTelemetryMapper:
    """Conservative mapper that withholds local vectors until RR-104."""

    def __init__(
        self,
        axis_transform: Optional[AxisTransform] = None,
        angular_velocity_transform: Optional[AxisTransform] = None,
        orientation_transform: Optional[AxisTransform] = None,
    ):
        self.axis_transform = axis_transform
        self.angular_velocity_transform = angular_velocity_transform
        self.orientation_transform = orientation_transform

    @classmethod
    def shanghai_rs3_tcr_v1(cls) -> "RaceRoomTelemetryMapper":
        """RR-104 mapping validated with the first low-speed pilot trace."""

        validation_id = "rr35_shanghai2021_layout2027_car11325_20260802_v1"
        return cls(
            axis_transform=AxisTransform(
                indices=(2, 0, 1),
                signs=(-1.0, 1.0, 1.0),
                validation_id=validation_id,
            ),
            # R3E's vehicle basis changes handedness when converted to
            # forward/left/up, so angular pseudovectors need the determinant
            # sign in addition to the linear-axis permutation.
            angular_velocity_transform=AxisTransform(
                indices=(2, 0, 1),
                signs=(1.0, -1.0, -1.0),
                validation_id=validation_id,
            ),
            orientation_transform=AxisTransform(
                indices=(2, 0, 1),
                signs=(1.0, -1.0, -1.0),
                validation_id=validation_id,
            ),
        )

    def map(self, snapshot: SharedMemorySnapshot) -> TelemetryFrame:
        data = snapshot.data
        player = data.player

        position = _vec3(player.position)
        orientation = None
        local_velocity = None
        local_acceleration = None
        local_angular_velocity = None
        if self.axis_transform is not None:
            local_velocity = self.axis_transform.apply(player.local_velocity)
            local_acceleration = self.axis_transform.apply(player.local_acceleration)
        if self.angular_velocity_transform is not None:
            local_angular_velocity = self.angular_velocity_transform.apply(
                player.local_angular_velocity
            )
        if self.orientation_transform is not None:
            orientation = self.orientation_transform.apply(player.orientation)

        lap_fraction = _optional_nonnegative(data.lap_distance_fraction)
        if lap_fraction is not None and lap_fraction > 1.0:
            lap_fraction = None

        lap_valid = _optional_flag(int(data.current_lap_valid))
        if lap_valid is None and int(data.lap_valid_state) in (0, 1, 2):
            lap_valid = int(data.lap_valid_state) == 0

        throttle = _optional_nonnegative(data.throttle_raw)
        brake = _optional_nonnegative(data.brake_raw)
        steering = (
            float(data.steer_input_raw)
            if _finite(data.steer_input_raw)
            else None
        )
        ffb = (
            float(player.steering_force_percentage)
            if _finite(player.steering_force_percentage)
            else None
        )
        rpm = (
            float(data.engine_rps) * 60.0 / (2.0 * math.pi)
            if _finite(data.engine_rps) and data.engine_rps >= 0.0
            else None
        )
        speed = _optional_nonnegative(data.car_speed)
        gear = int(data.gear) if int(data.gear) >= -1 else None

        availability = {
            "position_xyz_m": position is not None,
            "orientation_rpy_rad": orientation is not None,
            "local_velocity_xyz_mps": local_velocity is not None,
            "local_acceleration_xyz_mps2": local_acceleration is not None,
            "local_angular_velocity_xyz_radps": local_angular_velocity
            is not None,
            "steering_normalized": steering is not None,
            "throttle_normalized": throttle is not None,
            "brake_normalized": brake is not None,
            "ffb_normalized": ffb is not None,
            "lap_fraction": lap_fraction is not None,
            "lap_valid": lap_valid is not None,
            "in_pitlane": int(data.in_pitlane) in (0, 1),
            "axis_mapping_verified": self.axis_transform is not None,
            "angular_velocity_mapping_verified": self.angular_velocity_transform
            is not None,
            "orientation_mapping_verified": self.orientation_transform
            is not None,
        }

        return TelemetryFrame(
            schema_version=TELEMETRY_SCHEMA_VERSION,
            simulator="raceroom",
            sequence=int(player.game_simulation_ticks),
            simulation_time_s=float(player.game_simulation_time),
            received_at_s=snapshot.received_at_s,
            speed_mps=speed,
            rpm=rpm,
            gear=gear,
            position_xyz_m=position,
            orientation_rpy_rad=orientation,
            local_velocity_xyz_mps=local_velocity,
            local_acceleration_xyz_mps2=local_acceleration,
            local_angular_velocity_xyz_radps=local_angular_velocity,
            steering_normalized=steering,
            throttle_normalized=throttle,
            brake_normalized=brake,
            ffb_normalized=ffb,
            lap_fraction=lap_fraction,
            completed_laps=int(data.completed_laps),
            lap_valid=lap_valid,
            in_pitlane=_optional_flag(int(data.in_pitlane)),
            game_mode=int(data.game_mode),
            session_type=int(data.session_type),
            session_phase=int(data.session_phase),
            control_type=int(data.control_type),
            availability=availability,
            raw={
                "track_id": int(data.track_id),
                "layout_id": int(data.layout_id),
                "car_id": int(data.vehicle_info.model_id),
                "track_name": decode_u8_string(data.track_name),
                "layout_name": decode_u8_string(data.layout_name),
                "sequence_reset": snapshot.sequence_reset,
                "axis_validation_id": (
                    self.axis_transform.validation_id
                    if self.axis_transform is not None
                    else None
                ),
                "local_velocity_r3e_xyz": _vec3(player.local_velocity),
                "orientation_r3e_xyz": _vec3(player.orientation),
                "local_acceleration_r3e_xyz": _vec3(
                    player.local_acceleration
                ),
                "local_angular_velocity_r3e_xyz": _vec3(
                    player.local_angular_velocity
                ),
            },
        )
