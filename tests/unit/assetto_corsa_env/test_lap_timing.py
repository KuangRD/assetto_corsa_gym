import pytest

from assetto_corsa_gym.AssettoCorsaEnv.lap_timing import (
    PhysicalLapTimer,
    physical_lap_times,
)


def state(distance, timestamp):
    return {
        "LapDist": distance,
        "timestamp_ac": timestamp,
        "timestamp_env": timestamp + 1000,
    }


def test_counts_first_lap_when_episode_starts_in_start_zone():
    timer = PhysicalLapTimer(1000.0)
    timer.reset(5.0, 10.0)

    assert timer.update(995.0, 69.0) is None
    assert timer.update(5.0, 70.0) == pytest.approx(60.0)


def test_discards_partial_out_lap_after_mid_lap_reset():
    timer = PhysicalLapTimer(1000.0)
    timer.reset(500.0, 10.0)

    assert timer.update(995.0, 39.0) is None
    assert timer.update(5.0, 40.0) is None
    assert timer.update(995.0, 99.0) is None
    assert timer.update(5.0, 100.0) == pytest.approx(60.0)


def test_ignores_non_crossing_backward_or_small_position_changes():
    timer = PhysicalLapTimer(1000.0)
    timer.reset(10.0, 0.0)

    assert timer.update(900.0, 20.0) is None
    assert timer.update(700.0, 21.0) is None
    assert timer.update(710.0, 22.0) is None


def test_physical_lap_times_uses_simulator_timestamp_and_complete_laps_only():
    states = [
        state(500.0, 0.0),
        state(995.0, 29.0),
        state(5.0, 30.0),
        state(995.0, 89.0),
        state(5.0, 90.0),
        state(995.0, 149.0),
        state(5.0, 150.0),
    ]

    assert physical_lap_times(states, 1000.0) == pytest.approx([60.0, 60.0])


def test_state_timestamp_falls_back_to_environment_clock():
    timer = PhysicalLapTimer(1000.0)
    timer.reset_state({"LapDist": 5.0, "timestamp_env": 10.0})

    assert timer.update_state(
        {"LapDist": 995.0, "timestamp_env": 69.0}) is None
    assert timer.update_state(
        {"LapDist": 5.0, "timestamp_env": 70.0}) == pytest.approx(60.0)
