import ctypes
import unittest

from assetto_corsa_gym.RaceRoom.structures import (
    PLAYER_TICK_OFFSET,
    R3EDriverData,
    R3EDriverInfo,
    R3EPlayerData,
    R3EShared,
    SHARED_MEMORY_SIZE,
)


class OfficialLayoutTests(unittest.TestCase):
    """Fixtures cross-checked with the official API 3.5 C# layout."""

    def test_struct_sizes(self):
        self.assertEqual(ctypes.sizeof(R3EPlayerData), 560)
        self.assertEqual(ctypes.sizeof(R3EDriverInfo), 128)
        self.assertEqual(ctypes.sizeof(R3EDriverData), 328)
        self.assertEqual(SHARED_MEMORY_SIZE, 43996)

    def test_key_offsets(self):
        expected = {
            "version_major": 0,
            "version_minor": 4,
            "all_drivers_offset": 8,
            "driver_data_size": 12,
            "game_mode": 16,
            "player": 40,
            "track_name": 600,
            "session_type": 780,
            "session_phase": 796,
            "completed_laps": 1028,
            "lap_distance_fraction": 1044,
            "control_type": 1388,
            "car_speed": 1392,
            "engine_rps": 1396,
            "gear": 1408,
            "throttle_raw": 1504,
            "brake_raw": 1512,
            "steer_input_raw": 1524,
            "num_cars": 2008,
            "all_drivers_data": 2012,
        }
        for field, offset in expected.items():
            with self.subTest(field=field):
                self.assertEqual(getattr(R3EShared, field).offset, offset)
        self.assertEqual(PLAYER_TICK_OFFSET, 44)


if __name__ == "__main__":
    unittest.main()
