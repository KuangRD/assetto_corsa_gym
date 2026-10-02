import pytest

from assetto_corsa_gym.AssettoCorsaEnv.control_state import (
    has_low_speed_high_gear_conflict,
)


@pytest.mark.parametrize(
    "gear,speed,step",
    [
        (7, 15.0, 120),
        (8, 30.0, 250),
    ],
)
def test_detects_low_speed_high_gear_near_start(gear, speed, step):
    assert has_low_speed_high_gear_conflict(gear, speed, step)


@pytest.mark.parametrize(
    "gear,speed,step",
    [
        (6, 15.0, 120),
        (7, 30.1, 120),
        (7, 15.0, 251),
        (None, 15.0, 120),
    ],
)
def test_allows_normal_or_out_of_scope_states(gear, speed, step):
    assert not has_low_speed_high_gear_conflict(gear, speed, step)
