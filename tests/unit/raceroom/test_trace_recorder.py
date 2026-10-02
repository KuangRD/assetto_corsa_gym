import ctypes
import importlib.util
import unittest
from pathlib import Path

from assetto_corsa_gym.RaceRoom.shared_memory import SharedMemorySnapshot
from assetto_corsa_gym.RaceRoom.structures import R3EDriverData, R3EShared


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "raceroom_record_trace.py"
SPEC = importlib.util.spec_from_file_location("raceroom_record_trace", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class TraceRecorderTests(unittest.TestCase):
    def test_row_has_typed_core_fields_and_no_identity(self):
        data = R3EShared()
        data.version_major = 3
        data.version_minor = 5
        data.all_drivers_offset = R3EShared.num_cars.offset
        data.driver_data_size = ctypes.sizeof(R3EDriverData)
        data.player.user_id = 987654
        data.player.game_simulation_ticks = 42
        data.vehicle_info.model_id = 11325
        data.track_id = 2021
        data.layout_id = 2027
        data.player.local_velocity.z = -12.5
        snapshot = SharedMemorySnapshot(data, bytes(data), 10.0)

        row = MODULE.snapshot_to_row(snapshot, "straight")

        self.assertEqual(row["game_simulation_ticks"], 42)
        self.assertEqual(row["car_id"], 11325)
        self.assertEqual(row["local_velocity_z"], -12.5)
        self.assertNotIn("user_id", row)
        self.assertNotIn("player_name", row)


if __name__ == "__main__":
    unittest.main()
