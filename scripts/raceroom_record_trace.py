"""Record a de-identified RaceRoom telemetry segment as typed Parquet."""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import pyarrow as pa
import pyarrow.parquet as pq

from assetto_corsa_gym.RaceRoom.shared_memory import (
    RaceRoomSharedMemory,
    SharedMemorySnapshot,
)
from assetto_corsa_gym.RaceRoom.structures import decode_u8_string
from assetto_corsa_gym.RaceRoom.version import (
    ADAPTER_VERSION,
    OFFICIAL_API_COMMIT,
)
from assetto_corsa_gym.RacingEnv.errors import SimulatorError, TelemetryTimeoutError


TRACE_SCHEMA = pa.schema(
    [
        ("segment", pa.string()),
        ("received_at_s", pa.float64()),
        ("game_simulation_ticks", pa.int32()),
        ("game_simulation_time_s", pa.float64()),
        ("game_mode", pa.int32()),
        ("session_type", pa.int32()),
        ("session_phase", pa.int32()),
        ("control_type", pa.int32()),
        ("track_id", pa.int32()),
        ("layout_id", pa.int32()),
        ("car_id", pa.int32()),
        ("position_x", pa.float64()),
        ("position_y", pa.float64()),
        ("position_z", pa.float64()),
        ("orientation_x", pa.float64()),
        ("orientation_y", pa.float64()),
        ("orientation_z", pa.float64()),
        ("velocity_x", pa.float64()),
        ("velocity_y", pa.float64()),
        ("velocity_z", pa.float64()),
        ("local_velocity_x", pa.float64()),
        ("local_velocity_y", pa.float64()),
        ("local_velocity_z", pa.float64()),
        ("local_acceleration_x", pa.float64()),
        ("local_acceleration_y", pa.float64()),
        ("local_acceleration_z", pa.float64()),
        ("local_angular_velocity_x", pa.float64()),
        ("local_angular_velocity_y", pa.float64()),
        ("local_angular_velocity_z", pa.float64()),
        ("car_speed_mps", pa.float32()),
        ("engine_rps", pa.float32()),
        ("gear", pa.int32()),
        ("steer_input_raw", pa.float32()),
        ("throttle_raw", pa.float32()),
        ("brake_raw", pa.float32()),
        ("lap_distance_fraction", pa.float32()),
        ("completed_laps", pa.int32()),
        ("current_lap_valid", pa.int32()),
        ("in_pitlane", pa.int32()),
    ]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record official $R3E telemetry without player identity fields."
    )
    parser.add_argument("--label", required=True)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def snapshot_to_row(
    snapshot: SharedMemorySnapshot, segment: str
) -> Dict[str, Any]:
    data = snapshot.data
    player = data.player
    return {
        "segment": segment,
        "received_at_s": snapshot.received_at_s,
        "game_simulation_ticks": int(player.game_simulation_ticks),
        "game_simulation_time_s": float(player.game_simulation_time),
        "game_mode": int(data.game_mode),
        "session_type": int(data.session_type),
        "session_phase": int(data.session_phase),
        "control_type": int(data.control_type),
        "track_id": int(data.track_id),
        "layout_id": int(data.layout_id),
        "car_id": int(data.vehicle_info.model_id),
        "position_x": float(player.position.x),
        "position_y": float(player.position.y),
        "position_z": float(player.position.z),
        "orientation_x": float(player.orientation.x),
        "orientation_y": float(player.orientation.y),
        "orientation_z": float(player.orientation.z),
        "velocity_x": float(player.velocity.x),
        "velocity_y": float(player.velocity.y),
        "velocity_z": float(player.velocity.z),
        "local_velocity_x": float(player.local_velocity.x),
        "local_velocity_y": float(player.local_velocity.y),
        "local_velocity_z": float(player.local_velocity.z),
        "local_acceleration_x": float(player.local_acceleration.x),
        "local_acceleration_y": float(player.local_acceleration.y),
        "local_acceleration_z": float(player.local_acceleration.z),
        "local_angular_velocity_x": float(player.local_angular_velocity.x),
        "local_angular_velocity_y": float(player.local_angular_velocity.y),
        "local_angular_velocity_z": float(player.local_angular_velocity.z),
        "car_speed_mps": float(data.car_speed),
        "engine_rps": float(data.engine_rps),
        "gear": int(data.gear),
        "steer_input_raw": float(data.steer_input_raw),
        "throttle_raw": float(data.throttle_raw),
        "brake_raw": float(data.brake_raw),
        "lap_distance_fraction": float(data.lap_distance_fraction),
        "completed_laps": int(data.completed_laps),
        "current_lap_valid": int(data.current_lap_valid),
        "in_pitlane": int(data.in_pitlane),
    }


def record_segment(
    label: str, duration_s: float, timeout_s: float
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    reader = RaceRoomSharedMemory()
    rows: List[Dict[str, Any]] = []
    started = time.perf_counter()
    timeouts = 0
    try:
        snapshot = reader.open()
        rows.append(snapshot_to_row(snapshot, label))
        sequence = snapshot.sequence
        deadline = started + duration_s
        while time.perf_counter() < deadline:
            remaining = deadline - time.perf_counter()
            try:
                snapshot = reader.wait_for_snapshot(
                    sequence, min(timeout_s, max(remaining, 0.001))
                )
            except TelemetryTimeoutError:
                timeouts += 1
                if time.perf_counter() >= deadline:
                    break
                continue
            rows.append(snapshot_to_row(snapshot, label))
            sequence = snapshot.sequence

        data = snapshot.data
        metadata = {
            "format_version": "raceroom_trace_v1",
            "deidentified": True,
            "excluded_fields": ["player_name", "user_id", "driver_names"],
            "adapter_version": ADAPTER_VERSION,
            "official_api_commit": OFFICIAL_API_COMMIT,
            "api_version": "{}.{}".format(
                int(data.version_major), int(data.version_minor)
            ),
            "segment": label,
            "duration_s": time.perf_counter() - started,
            "rows": len(rows),
            "first_sequence": rows[0]["game_simulation_ticks"],
            "last_sequence": rows[-1]["game_simulation_ticks"],
            "track_name": decode_u8_string(data.track_name),
            "layout_name": decode_u8_string(data.layout_name),
            "track_id": int(data.track_id),
            "layout_id": int(data.layout_id),
            "car_id": int(data.vehicle_info.model_id),
            "game_mode": int(data.game_mode),
            "session_type": int(data.session_type),
            "control_type": int(data.control_type),
            "timeouts": timeouts,
            "duplicate_sequences": reader.stats.duplicate_sequences,
            "torn_read_retries": reader.stats.torn_read_retries,
            "sequence_resets": reader.stats.sequence_resets,
        }
        return rows, metadata
    finally:
        reader.close()


def main() -> int:
    args = parse_args()
    try:
        rows, metadata = record_segment(args.label, args.duration, args.timeout)
    except SimulatorError as error:
        print("RaceRoom trace recording failed: {}".format(error), file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=TRACE_SCHEMA)
    pq.write_table(table, args.output, compression="zstd")
    metadata_path = args.output.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"parquet": str(args.output), **metadata}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
