"""Read-only RaceRoom shared-memory probe for M1 validation."""

import argparse
import json
import math
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from assetto_corsa_gym.RaceRoom.mapper import RaceRoomTelemetryMapper
from assetto_corsa_gym.RaceRoom.shared_memory import RaceRoomSharedMemory
from assetto_corsa_gym.RaceRoom.structures import decode_u8_string
from assetto_corsa_gym.RaceRoom.version import (
    ADAPTER_VERSION,
    OFFICIAL_API_COMMIT,
)
from assetto_corsa_gym.RacingEnv.errors import SimulatorError, TelemetryTimeoutError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe the official $R3E map without enabling controls."
    )
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print the JSON report."
    )
    return parser.parse_args()


def vec3(value: Any) -> List[float]:
    return [float(value.x), float(value.y), float(value.z)]


def finite_or_none(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def run_probe(duration_s: float, timeout_s: float) -> Dict[str, Any]:
    reader = RaceRoomSharedMemory()
    mapper = RaceRoomTelemetryMapper()
    started = time.perf_counter()
    wall_arrivals: List[float] = []
    tick_deltas: List[int] = []
    timeouts = 0

    try:
        initial = reader.open()
        latest = initial
        previous_sequence = initial.sequence
        wall_arrivals.append(initial.received_at_s)
        deadline = started + duration_s

        while time.perf_counter() < deadline:
            remaining = deadline - time.perf_counter()
            try:
                latest = reader.wait_for_snapshot(
                    previous_sequence, min(timeout_s, max(remaining, 0.001))
                )
            except TelemetryTimeoutError:
                timeouts += 1
                continue
            tick_deltas.append(latest.sequence - previous_sequence)
            previous_sequence = latest.sequence
            wall_arrivals.append(latest.received_at_s)

        data = latest.data
        frame = mapper.map(latest)
        intervals = [
            later - earlier
            for earlier, later in zip(wall_arrivals, wall_arrivals[1:])
            if later > earlier
        ]
        observed_hz = 1.0 / mean(intervals) if intervals else 0.0
        positive_tick_deltas = [value for value in tick_deltas if value > 0]
        return {
            "probe": {
                "duration_s": time.perf_counter() - started,
                "adapter_version": ADAPTER_VERSION,
                "official_api_commit": OFFICIAL_API_COMMIT,
                "read_only": True,
            },
            "api": {
                "major": int(data.version_major),
                "minor": int(data.version_minor),
                "all_drivers_offset": int(data.all_drivers_offset),
                "driver_data_size": int(data.driver_data_size),
            },
            "session": {
                "game_mode": int(data.game_mode),
                "session_type": int(data.session_type),
                "session_phase": int(data.session_phase),
                "control_type": int(data.control_type),
                "track_name": decode_u8_string(data.track_name),
                "layout_name": decode_u8_string(data.layout_name),
                "track_id": int(data.track_id),
                "layout_id": int(data.layout_id),
                "car_id": int(data.vehicle_info.model_id),
            },
            "frequency": {
                "new_frames": max(len(wall_arrivals) - 1, 0),
                "observed_hz": observed_hz,
                "mean_physics_tick_delta": (
                    mean(positive_tick_deltas) if positive_tick_deltas else None
                ),
                "timeouts": timeouts,
                "duplicate_sequences": reader.stats.duplicate_sequences,
                "torn_read_retries": reader.stats.torn_read_retries,
                "sequence_resets": reader.stats.sequence_resets,
            },
            "latest": {
                "sequence": frame.sequence,
                "simulation_time_s": finite_or_none(frame.simulation_time_s),
                "speed_mps": finite_or_none(frame.speed_mps),
                "rpm": finite_or_none(frame.rpm),
                "gear": frame.gear,
                "lap_fraction": frame.lap_fraction,
                "completed_laps": frame.completed_laps,
                "lap_valid": frame.lap_valid,
                "steering_raw": frame.steering_normalized,
                "throttle_raw": frame.throttle_normalized,
                "brake_raw": frame.brake_normalized,
                "world_position_r3e_xyz": vec3(data.player.position),
                "orientation_r3e_xyz": vec3(data.player.orientation),
                "local_velocity_r3e_xyz": vec3(data.player.local_velocity),
                "local_acceleration_r3e_xyz": vec3(
                    data.player.local_acceleration
                ),
                "local_angular_velocity_r3e_xyz": vec3(
                    data.player.local_angular_velocity
                ),
            },
            "availability": dict(frame.availability),
            "next_action": (
                "Run RR-104 stationary/straight/left/right experiments; do not "
                "enable vJoy until axis_mapping_validation_id is frozen."
            ),
        }
    finally:
        reader.close()


def main() -> int:
    args = parse_args()
    try:
        report = run_probe(args.duration, args.timeout)
    except SimulatorError as error:
        print("RaceRoom probe failed: {}".format(error), file=sys.stderr)
        return 2

    indent = 2 if args.pretty else None
    rendered = json.dumps(report, indent=indent, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
