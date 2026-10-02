"""Deny-by-default safety checks for any automated RaceRoom control."""

from dataclasses import dataclass
from typing import Optional, Tuple

from assetto_corsa_gym.RacingEnv.errors import UnsafeSessionError

from .constants import ControlType, GameMode, SessionPhase
from .structures import R3EShared


@dataclass(frozen=True)
class SessionGuardPolicy:
    expected_track_id: Optional[int] = None
    expected_layout_id: Optional[int] = None
    expected_car_id: Optional[int] = None
    allowed_game_modes: Tuple[int, ...] = (int(GameMode.TRACK_TEST),)
    allowed_session_phases: Tuple[int, ...] = (int(SessionPhase.GREEN),)


@dataclass(frozen=True)
class SessionGuardDecision:
    allowed: bool
    reasons: Tuple[str, ...]


class RaceRoomSessionGuard:
    def __init__(self, policy: Optional[SessionGuardPolicy] = None):
        self.policy = policy or SessionGuardPolicy()

    def evaluate(self, data: R3EShared) -> SessionGuardDecision:
        reasons = []
        if int(data.game_mode) not in self.policy.allowed_game_modes:
            reasons.append("game_mode={}".format(int(data.game_mode)))
        if int(data.session_phase) not in self.policy.allowed_session_phases:
            reasons.append("session_phase={}".format(int(data.session_phase)))
        if int(data.control_type) != int(ControlType.PLAYER):
            reasons.append("control_type={}".format(int(data.control_type)))
        if int(data.game_paused) != 0:
            reasons.append("game_paused")
        if int(data.game_in_menus) != 0:
            reasons.append("game_in_menus")
        if int(data.game_in_replay) != 0:
            reasons.append("game_in_replay")
        if int(data.game_player_in_garage) != 0:
            reasons.append("player_in_garage")

        expected_values = (
            ("track_id", self.policy.expected_track_id, int(data.track_id)),
            ("layout_id", self.policy.expected_layout_id, int(data.layout_id)),
            ("car_id", self.policy.expected_car_id, int(data.vehicle_info.model_id)),
        )
        for name, expected, actual in expected_values:
            if expected is not None and actual != expected:
                reasons.append("{}={} expected={}".format(name, actual, expected))
        return SessionGuardDecision(not reasons, tuple(reasons))

    def assert_control_allowed(self, data: R3EShared) -> None:
        decision = self.evaluate(data)
        if not decision.allowed:
            raise UnsafeSessionError(
                "RaceRoom automated control denied: {}".format(
                    ", ".join(decision.reasons)
                )
            )
