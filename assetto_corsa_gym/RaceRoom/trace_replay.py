"""Replay de-identified RaceRoom Parquet traces without launching the game."""

import ctypes
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyarrow.parquet as pq

from assetto_corsa_gym.RacingEnv.types import TelemetryFrame

from .mapper import RaceRoomTelemetryMapper
from .shared_memory import SharedMemorySnapshot
from .structures import R3EDriverData, R3EShared


REQUIRED_COLUMNS = frozenset(
    {
        "received_at_s",
        "game_simulation_ticks",
        "game_simulation_time_s",
        "game_mode",
        "session_type",
        "session_phase",
        "control_type",
        "track_id",
        "layout_id",
        "car_id",
        "position_x",
        "position_y",
        "position_z",
        "orientation_x",
        "orientation_y",
        "orientation_z",
        "local_velocity_x",
        "local_velocity_y",
        "local_velocity_z",
        "local_acceleration_x",
        "local_acceleration_y",
        "local_acceleration_z",
        "local_angular_velocity_x",
        "local_angular_velocity_y",
        "local_angular_velocity_z",
        "car_speed_mps",
        "engine_rps",
        "gear",
        "steer_input_raw",
        "throttle_raw",
        "brake_raw",
        "lap_distance_fraction",
        "completed_laps",
        "current_lap_valid",
        "in_pitlane",
    }
)


class RaceRoomTraceReplay:
    """Step, accelerated, or real-time replay of a recorded typed trace."""

    def __init__(
        self,
        path: Path,
        mapper: Optional[RaceRoomTelemetryMapper] = None,
        replay_speed: float = 0.0,
    ):
        self.path = Path(path)
        self.mapper = mapper or RaceRoomTelemetryMapper.shanghai_rs3_tcr_v1()
        self.replay_speed = replay_speed
        self.rows: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.index = 0
        self._last_simulation_time: Optional[float] = None

    def open(self) -> None:
        parquet_file = pq.ParquetFile(self.path)
        columns = set(parquet_file.schema.names)
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError("RaceRoom trace is missing columns: {}".format(missing))
        self.rows = parquet_file.read().to_pylist()
        if not self.rows:
            raise ValueError("RaceRoom trace contains no rows")
        metadata_path = self.path.with_suffix(".metadata.json")
        if metadata_path.exists():
            self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.reset()

    def close(self) -> None:
        self.rows = []
        self.index = 0
        self._last_simulation_time = None

    def reset(self) -> None:
        self.index = 0
        self._last_simulation_time = None

    def __len__(self) -> int:
        return len(self.rows)

    def _pace(self, simulation_time_s: float) -> None:
        if self.replay_speed > 0.0 and self._last_simulation_time is not None:
            delay = (
                simulation_time_s - self._last_simulation_time
            ) / self.replay_speed
            if delay > 0.0:
                time.sleep(delay)
        self._last_simulation_time = simulation_time_s

    @staticmethod
    def _row_to_snapshot(row: Dict[str, Any]) -> SharedMemorySnapshot:
        data = R3EShared()
        data.version_major = 3
        data.version_minor = 5
        data.all_drivers_offset = R3EShared.num_cars.offset
        data.driver_data_size = ctypes.sizeof(R3EDriverData)
        data.game_mode = int(row["game_mode"])
        data.session_type = int(row["session_type"])
        data.session_phase = int(row["session_phase"])
        data.control_type = int(row["control_type"])
        data.track_id = int(row["track_id"])
        data.layout_id = int(row["layout_id"])
        data.vehicle_info.model_id = int(row["car_id"])
        data.player.game_simulation_ticks = int(row["game_simulation_ticks"])
        data.player.game_simulation_time = float(row["game_simulation_time_s"])

        for prefix, target in (
            ("position", data.player.position),
            ("orientation", data.player.orientation),
            ("local_velocity", data.player.local_velocity),
            ("local_acceleration", data.player.local_acceleration),
            ("local_angular_velocity", data.player.local_angular_velocity),
        ):
            target.x = float(row[prefix + "_x"])
            target.y = float(row[prefix + "_y"])
            target.z = float(row[prefix + "_z"])

        data.car_speed = float(row["car_speed_mps"])
        data.engine_rps = float(row["engine_rps"])
        data.gear = int(row["gear"])
        data.steer_input_raw = float(row["steer_input_raw"])
        data.throttle_raw = float(row["throttle_raw"])
        data.brake_raw = float(row["brake_raw"])
        data.lap_distance_fraction = float(row["lap_distance_fraction"])
        data.completed_laps = int(row["completed_laps"])
        data.current_lap_valid = int(row["current_lap_valid"])
        data.in_pitlane = int(row["in_pitlane"])
        return SharedMemorySnapshot(
            data=data,
            payload=bytes(data),
            received_at_s=float(row["received_at_s"]),
        )

    def next_frame(self) -> TelemetryFrame:
        if not self.rows:
            raise RuntimeError("RaceRoom trace replay is not open")
        if self.index >= len(self.rows):
            raise StopIteration
        row = self.rows[self.index]
        self.index += 1
        simulation_time = float(row["game_simulation_time_s"])
        self._pace(simulation_time)
        return self.mapper.map(self._row_to_snapshot(row))

    def wait_for_frame(
        self, after_sequence: int, timeout_s: float = 0.0
    ) -> TelemetryFrame:
        del timeout_s
        while True:
            frame = self.next_frame()
            if frame.sequence > after_sequence:
                return frame
