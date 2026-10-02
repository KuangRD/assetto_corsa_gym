import ctypes
import math
import unittest

from assetto_corsa_gym.RaceRoom.mapper import AxisTransform, RaceRoomTelemetryMapper
from assetto_corsa_gym.RaceRoom.shared_memory import SharedMemorySnapshot
from assetto_corsa_gym.RaceRoom.structures import R3EDriverData, R3EShared


def make_snapshot():
    data = R3EShared()
    data.version_major = 3
    data.version_minor = 5
    data.all_drivers_offset = R3EShared.num_cars.offset
    data.driver_data_size = ctypes.sizeof(R3EDriverData)
    data.player.game_simulation_ticks = 400
    data.player.game_simulation_time = 1.0
    data.player.position.x = 10.0
    data.player.position.y = 2.0
    data.player.position.z = -5.0
    data.player.local_velocity.x = 1.0
    data.player.local_velocity.y = 2.0
    data.player.local_velocity.z = 3.0
    data.player.local_acceleration.x = 4.0
    data.player.local_acceleration.y = 5.0
    data.player.local_acceleration.z = 6.0
    data.player.local_angular_velocity.x = 7.0
    data.player.local_angular_velocity.y = 8.0
    data.player.local_angular_velocity.z = 9.0
    data.car_speed = 20.0
    data.engine_rps = 100.0
    data.gear = 3
    data.throttle_raw = 0.5
    data.brake_raw = 0.25
    data.steer_input_raw = -0.5
    data.lap_distance_fraction = 0.75
    data.completed_laps = 2
    data.current_lap_valid = 1
    data.in_pitlane = 0
    return SharedMemorySnapshot(data, bytes(data), received_at_s=123.0)


class MapperTests(unittest.TestCase):
    def test_units_and_basic_fields(self):
        frame = RaceRoomTelemetryMapper().map(make_snapshot())
        self.assertEqual(frame.sequence, 400)
        self.assertEqual(frame.speed_mps, 20.0)
        self.assertAlmostEqual(frame.rpm, 100.0 * 60.0 / (2.0 * math.pi))
        self.assertEqual(frame.gear, 3)
        self.assertEqual(frame.position_xyz_m, (10.0, 2.0, -5.0))
        self.assertEqual(frame.lap_fraction, 0.75)
        self.assertTrue(frame.lap_valid)
        self.assertFalse(frame.in_pitlane)

    def test_unverified_local_axes_are_withheld(self):
        frame = RaceRoomTelemetryMapper().map(make_snapshot())
        self.assertIsNone(frame.local_velocity_xyz_mps)
        self.assertIsNone(frame.orientation_rpy_rad)
        self.assertFalse(frame.availability["axis_mapping_verified"])
        self.assertFalse(
            frame.availability["angular_velocity_mapping_verified"]
        )
        self.assertFalse(frame.availability["orientation_mapping_verified"])
        self.assertEqual(frame.raw["local_velocity_r3e_xyz"], (1.0, 2.0, 3.0))

    def test_explicit_axis_transform_is_applied(self):
        transform = AxisTransform(
            indices=(2, 0, 1), signs=(-1.0, 1.0, 1.0), validation_id="fixture"
        )
        frame = RaceRoomTelemetryMapper(transform).map(make_snapshot())
        self.assertEqual(frame.local_velocity_xyz_mps, (-3.0, 1.0, 2.0))
        self.assertTrue(frame.availability["axis_mapping_verified"])
        self.assertEqual(frame.raw["axis_validation_id"], "fixture")

    def test_validated_pilot_mapping_handles_linear_and_angular_handedness(self):
        snapshot = make_snapshot()
        snapshot.data.player.orientation.x = 10.0
        snapshot.data.player.orientation.y = 20.0
        snapshot.data.player.orientation.z = 30.0
        frame = RaceRoomTelemetryMapper.shanghai_rs3_tcr_v1().map(snapshot)
        self.assertEqual(frame.local_velocity_xyz_mps, (-3.0, 1.0, 2.0))
        self.assertEqual(
            frame.local_angular_velocity_xyz_radps, (9.0, -7.0, -8.0)
        )
        self.assertEqual(frame.orientation_rpy_rad, (30.0, -10.0, -20.0))
        self.assertTrue(
            frame.availability["angular_velocity_mapping_verified"]
        )

    def test_unavailable_lap_fraction_is_none(self):
        snapshot = make_snapshot()
        snapshot.data.lap_distance_fraction = -1.0
        frame = RaceRoomTelemetryMapper().map(snapshot)
        self.assertIsNone(frame.lap_fraction)


if __name__ == "__main__":
    unittest.main()
