import unittest

from assetto_corsa_gym.RaceRoom.constants import ControlType, GameMode, SessionPhase
from assetto_corsa_gym.RaceRoom.session_guard import (
    RaceRoomSessionGuard,
    SessionGuardPolicy,
)
from assetto_corsa_gym.RaceRoom.structures import R3EShared
from assetto_corsa_gym.RacingEnv.errors import UnsafeSessionError


def safe_data():
    data = R3EShared()
    data.game_mode = int(GameMode.TRACK_TEST)
    data.session_phase = int(SessionPhase.GREEN)
    data.control_type = int(ControlType.PLAYER)
    data.track_id = 2021
    data.layout_id = 2027
    data.vehicle_info.model_id = 11325
    return data


class SessionGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = RaceRoomSessionGuard(
            SessionGuardPolicy(
                expected_track_id=2021,
                expected_layout_id=2027,
                expected_car_id=11325,
            )
        )

    def test_exact_offline_pilot_session_is_allowed(self):
        self.assertTrue(self.guard.evaluate(safe_data()).allowed)

    def test_online_and_competition_modes_are_denied(self):
        for mode in (
            GameMode.MULTIPLAYER,
            GameMode.MULTIPLAYER_RANKED,
            GameMode.COMPETITION,
            GameMode.LEADERBOARD_CHALLENGE,
            GameMode.UNAVAILABLE,
        ):
            with self.subTest(mode=mode):
                data = safe_data()
                data.game_mode = int(mode)
                self.assertFalse(self.guard.evaluate(data).allowed)

    def test_replay_ai_pause_menu_and_garage_are_denied(self):
        mutations = (
            ("control_type", int(ControlType.AI)),
            ("control_type", int(ControlType.REPLAY)),
            ("game_paused", 1),
            ("game_in_menus", 1),
            ("game_in_replay", 1),
            ("game_player_in_garage", 1),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                data = safe_data()
                setattr(data, field, value)
                self.assertFalse(self.guard.evaluate(data).allowed)

    def test_wrong_pilot_asset_is_denied(self):
        data = safe_data()
        data.vehicle_info.model_id = 999
        with self.assertRaises(UnsafeSessionError):
            self.guard.assert_control_allowed(data)


if __name__ == "__main__":
    unittest.main()
