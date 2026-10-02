import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from assetto_corsa_gym.RaceRoom.trace_replay import (
    REQUIRED_COLUMNS,
    RaceRoomTraceReplay,
)


def row(sequence, speed, local_z):
    result = {name: 0 for name in REQUIRED_COLUMNS}
    result.update(
        {
            "received_at_s": float(sequence),
            "game_simulation_ticks": sequence,
            "game_simulation_time_s": sequence / 400.0,
            "game_mode": 0,
            "session_type": 0,
            "session_phase": 5,
            "control_type": 0,
            "track_id": 2021,
            "layout_id": 2027,
            "car_id": 11325,
            "car_speed_mps": speed,
            "local_velocity_z": local_z,
            "gear": 1,
            "current_lap_valid": 1,
            "in_pitlane": 0,
        }
    )
    return result


class TraceReplayTests(unittest.TestCase):
    def test_step_and_sequence_filtered_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.parquet"
            pq.write_table(
                pa.Table.from_pylist([row(10, 2.0, -2.0), row(11, 3.0, -3.0)]),
                path,
            )
            replay = RaceRoomTraceReplay(path)
            replay.open()
            first = replay.next_frame()
            second = replay.wait_for_frame(first.sequence)
            self.assertEqual(len(replay), 2)
            self.assertEqual(first.sequence, 10)
            self.assertEqual(first.local_velocity_xyz_mps, (2.0, 0.0, 0.0))
            self.assertEqual(second.sequence, 11)
            with self.assertRaises(StopIteration):
                replay.next_frame()

    def test_missing_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.parquet"
            pq.write_table(pa.table({"game_simulation_ticks": [1]}), path)
            with self.assertRaises(ValueError):
                RaceRoomTraceReplay(path).open()


if __name__ == "__main__":
    unittest.main()
