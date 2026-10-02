import pytest

from assetto_corsa_gym.AssettoCorsaEnv.steering_smoothness import (
    condition_seam_steering_command,
    condition_steering_guards,
    condition_strong_steering_reversal,
    compute_effective_steer_rate_limit,
    compute_distance_zone_weight,
    compute_periodic_seam_weight,
    compute_post_seam_weight,
    extend_latched_recovery_weight,
    compute_recovery_guard_weight,
    compute_recovery_steering_target,
    compute_seam_absolute_steer_limit,
    compute_steering_smoothness_terms,
    filter_steering_rate_command,
    limit_accumulated_steering,
    step_steering_toward_target,
    update_recovery_guard_latch,
)


BASE_ARGS = dict(
    steering_command=1.0,
    previous_steering_command=-1.0,
    steering_rate_deg_s=900.0,
    speed_m_s=40.0,
    gap_m=0.0,
    max_abs_curvature=0.0,
    training_step=1_800_000,
    command_coef=0.02,
    reversal_coef=0.04,
    rate_coef=0.05,
    jerk_coef=0.0,
    max_steer_rate_deg_s=900.0,
    min_speed_m_s=30.0,
    full_speed_m_s=40.0,
    curvature_threshold=0.0015,
    max_gap_m=3.0,
    ramp_start_step=1_700_000,
    ramp_steps=100_000,
)


def terms(**overrides):
    arguments = BASE_ARGS.copy()
    arguments.update(overrides)
    return compute_steering_smoothness_terms(**arguments)


def test_full_strength_saturated_reversal_has_expected_penalty():
    result = terms()

    assert result["straight_gate"] == pytest.approx(1.0)
    assert result["ramp"] == pytest.approx(1.0)
    assert result["command_penalty"] == pytest.approx(0.02)
    assert result["reversal_penalty"] == pytest.approx(0.04)
    assert result["rate_penalty"] == pytest.approx(0.05)
    assert result["total_penalty"] == pytest.approx(0.11)


def test_ramp_scales_all_terms_together():
    result = terms(training_step=1_725_000)

    assert result["ramp"] == pytest.approx(0.25)
    assert result["total_penalty"] == pytest.approx(0.0275)


@pytest.mark.parametrize(
    "overrides",
    [
        {"speed_m_s": 30.0},
        {"gap_m": 3.0},
        {"max_abs_curvature": 0.0015},
        {"training_step": 1_700_000},
    ],
)
def test_gate_disables_penalty_outside_target_state(overrides):
    result = terms(**overrides)

    assert result["total_penalty"] == pytest.approx(0.0)


def test_same_direction_commands_have_no_reversal_penalty():
    result = terms(previous_steering_command=0.5)

    assert result["reversal_penalty"] == pytest.approx(0.0)
    assert result["command_penalty"] > 0.0


def test_small_steering_rate_is_penalized_quadratically():
    result = terms(steering_rate_deg_s=90.0)

    assert result["rate_penalty"] == pytest.approx(0.0005)


def test_full_command_jump_has_normalized_jerk_penalty():
    result = terms(jerk_coef=0.08)

    assert result["jerk_penalty"] == pytest.approx(0.08)
    assert result["total_penalty"] == pytest.approx(0.19)


def test_global_reversal_and_jerk_remain_active_in_corners():
    result = terms(
        max_abs_curvature=0.01,
        global_reversal_coef=0.04,
        global_jerk_coef=0.02,
    )

    assert result["straight_gate"] == pytest.approx(0.0)
    assert result["command_penalty"] == pytest.approx(0.0)
    assert result["rate_penalty"] == pytest.approx(0.0)
    assert result["global_reversal_penalty"] == pytest.approx(0.04)
    assert result["global_jerk_penalty"] == pytest.approx(0.02)
    assert result["total_penalty"] == pytest.approx(0.06)


def test_global_terms_do_not_penalize_stable_corner_steering():
    result = terms(
        steering_command=0.8,
        previous_steering_command=0.8,
        max_abs_curvature=0.01,
        global_reversal_coef=0.04,
        global_jerk_coef=0.02,
    )

    assert result["total_penalty"] == pytest.approx(0.0)


def test_global_chatter_penalizes_only_second_immediate_reversal():
    chatter = terms(
        steering_command=1.0,
        previous_steering_command=-1.0,
        previous_previous_steering_command=1.0,
        max_abs_curvature=0.01,
        global_chatter_coef=0.04,
    )
    single_reversal = terms(
        steering_command=1.0,
        previous_steering_command=-1.0,
        previous_previous_steering_command=-1.0,
        max_abs_curvature=0.01,
        global_chatter_coef=0.04,
    )

    assert chatter["chatter_strength"] == pytest.approx(1.0)
    assert chatter["chatter_penalty"] == pytest.approx(0.04)
    assert single_reversal["chatter_penalty"] == pytest.approx(0.0)


def test_global_chatter_uses_smallest_command_magnitude():
    result = terms(
        steering_command=0.8,
        previous_steering_command=-0.5,
        previous_previous_steering_command=0.6,
        max_abs_curvature=0.01,
        global_chatter_coef=0.04,
    )

    assert result["chatter_strength"] == pytest.approx(0.25)
    assert result["chatter_penalty"] == pytest.approx(0.01)


def test_dynamic_rate_limit_blends_with_gate_and_ramp():
    assert compute_effective_steer_rate_limit(900.0, 600.0, 1.0, 1.0) == 600.0
    assert compute_effective_steer_rate_limit(900.0, 600.0, 0.5, 0.5) == 825.0
    assert compute_effective_steer_rate_limit(900.0, 600.0, 0.0, 1.0) == 900.0


def test_dynamic_rate_limit_rejects_higher_straight_limit():
    with pytest.raises(ValueError):
        compute_effective_steer_rate_limit(900.0, 1000.0, 1.0, 1.0)


@pytest.mark.parametrize("distance", [0.0, 20.0, 5784.0, 5804.0])
def test_periodic_seam_weight_is_full_on_both_sides(distance):
    assert compute_periodic_seam_weight(
        distance, 5804.0, 35.0, 100.0) == pytest.approx(1.0)


def test_periodic_seam_weight_fades_continuously():
    assert compute_periodic_seam_weight(
        67.5, 5804.0, 35.0, 100.0) == pytest.approx(0.5)
    assert compute_periodic_seam_weight(
        5804.0 - 67.5, 5804.0, 35.0, 100.0) == pytest.approx(0.5)
    assert compute_periodic_seam_weight(
        100.0, 5804.0, 35.0, 100.0) == pytest.approx(0.0)


def test_post_seam_weight_does_not_activate_before_finish_line():
    assert compute_post_seam_weight(
        5780.0, 5804.0, 180.0, 220.0) == pytest.approx(0.0)
    assert compute_post_seam_weight(
        100.0, 5804.0, 180.0, 220.0) == pytest.approx(1.0)
    assert compute_post_seam_weight(
        200.0, 5804.0, 180.0, 220.0) == pytest.approx(0.5)
    assert compute_post_seam_weight(
        220.0, 5804.0, 180.0, 220.0) == pytest.approx(0.0)


def test_emergency_recovery_extends_only_while_latched():
    assert extend_latched_recovery_weight(0.25, 0.75, False) == 0.25
    assert extend_latched_recovery_weight(0.25, 0.75, True) == 0.75
    assert extend_latched_recovery_weight(0.9, 0.75, True) == 0.9


def test_distance_zone_weight_has_smooth_entry_full_zone_and_exit():
    zone = (5040.0, 5080.0, 5180.0, 5200.0)
    assert compute_distance_zone_weight(5039.0, *zone) == pytest.approx(0.0)
    assert compute_distance_zone_weight(5060.0, *zone) == pytest.approx(0.5)
    assert compute_distance_zone_weight(5100.0, *zone) == pytest.approx(1.0)
    assert compute_distance_zone_weight(5190.0, *zone) == pytest.approx(0.5)
    assert compute_distance_zone_weight(5201.0, *zone) == pytest.approx(0.0)


def test_distance_zone_weight_rejects_overlapping_boundaries():
    with pytest.raises(ValueError):
        compute_distance_zone_weight(1.0, 0.0, 2.0, 2.0, 4.0)


def test_targeted_gate_floor_activates_penalty_when_curvature_gate_is_zero():
    result = terms(max_abs_curvature=0.01, straight_gate_floor=0.75)

    assert result["straight_gate"] == pytest.approx(0.75)
    assert result["total_penalty"] == pytest.approx(0.0825)


def test_seam_conditioner_clamps_and_damps_full_reversal_without_lag():
    result = condition_seam_steering_command(
        steering_command=-1.0,
        previous_conditioned_command=0.35,
        seam_weight=1.0,
        max_abs_command=0.35,
        reversal_damping=0.25,
    )

    assert result == pytest.approx(-0.0875)


def test_seam_conditioner_clamps_same_direction_without_damping():
    result = condition_seam_steering_command(
        steering_command=1.0,
        previous_conditioned_command=0.2,
        seam_weight=1.0,
        max_abs_command=0.35,
        reversal_damping=0.25,
    )

    assert result == pytest.approx(0.35)


def test_seam_conditioner_is_transparent_outside_guard():
    result = condition_seam_steering_command(
        steering_command=-1.0,
        previous_conditioned_command=0.35,
        seam_weight=0.0,
        max_abs_command=0.35,
        reversal_damping=0.25,
    )

    assert result == pytest.approx(-1.0)


def test_strong_reversal_guard_follows_new_direction_without_lag():
    result = condition_strong_steering_reversal(
        steering_command=-1.0,
        previous_policy_command=0.8,
        reversal_damping=0.35,
        minimum_reversal_magnitude=0.25,
    )

    assert result == pytest.approx(-0.35)


def test_strong_reversal_guard_leaves_single_weak_correction_unchanged():
    result = condition_strong_steering_reversal(
        steering_command=-0.2,
        previous_policy_command=0.8,
        reversal_damping=0.35,
        minimum_reversal_magnitude=0.25,
    )

    assert result == pytest.approx(-0.2)


def test_global_reversal_guard_is_used_outside_seam():
    result, global_active = condition_steering_guards(
        steering_command=-1.0,
        previous_policy_command=0.8,
        previous_conditioned_command=0.8,
        seam_weight=0.0,
        seam_max_abs_command=0.15,
        seam_reversal_damping=0.25,
        enable_global_reversal_guard=True,
        global_reversal_damping=0.35,
        global_minimum_reversal_magnitude=0.25,
    )

    assert result == pytest.approx(-0.35)
    assert global_active is True


def test_seam_guard_takes_precedence_over_global_guard():
    result, global_active = condition_steering_guards(
        steering_command=-1.0,
        previous_policy_command=0.8,
        previous_conditioned_command=0.15,
        seam_weight=1.0,
        seam_max_abs_command=0.15,
        seam_reversal_damping=0.25,
        enable_global_reversal_guard=True,
        global_reversal_damping=0.35,
        global_minimum_reversal_magnitude=0.25,
    )

    assert result == pytest.approx(-0.0375)
    assert global_active is False


def test_recovery_guard_is_full_near_reference_line():
    assert compute_recovery_guard_weight(
        gap_m=0.5,
        number_of_tyres_out=0,
        full_guard_gap_m=0.8,
        release_guard_gap_m=1.5,
    ) == pytest.approx(1.0)


def test_recovery_guard_fades_with_lateral_error():
    assert compute_recovery_guard_weight(
        gap_m=-1.15,
        number_of_tyres_out=0,
        full_guard_gap_m=0.8,
        release_guard_gap_m=1.5,
    ) == pytest.approx(0.5)


def test_recovery_guard_releases_at_large_gap_or_tyres_out():
    assert compute_recovery_guard_weight(
        gap_m=1.5,
        number_of_tyres_out=0,
        full_guard_gap_m=0.8,
        release_guard_gap_m=1.5,
    ) == pytest.approx(0.0)


def test_recovery_guard_can_ignore_a_single_curb_side_tyre():
    assert compute_recovery_guard_weight(
        gap_m=0.0,
        number_of_tyres_out=1,
        full_guard_gap_m=1.5,
        release_guard_gap_m=2.5,
        min_tyres_out_for_release=2,
    ) == pytest.approx(1.0)
    assert compute_recovery_guard_weight(
        gap_m=0.0,
        number_of_tyres_out=2,
        full_guard_gap_m=1.5,
        release_guard_gap_m=2.5,
        min_tyres_out_for_release=2,
    ) == pytest.approx(0.0)


def test_recovery_latch_requires_stable_frames_before_release():
    latched, safe_steps = update_recovery_guard_latch(
        False, 0, 0.5, 2, 2.5, 1.0, 2, 3)
    assert latched is True
    assert safe_steps == 0

    latched, safe_steps = update_recovery_guard_latch(
        latched, safe_steps, 0.5, 0, 2.5, 1.0, 2, 3)
    assert (latched, safe_steps) == (True, 1)
    latched, safe_steps = update_recovery_guard_latch(
        latched, safe_steps, 1.2, 0, 2.5, 1.0, 2, 3)
    assert (latched, safe_steps) == (True, 0)
    for expected in (1, 2):
        latched, safe_steps = update_recovery_guard_latch(
            latched, safe_steps, 0.5, 0, 2.5, 1.0, 2, 3)
        assert (latched, safe_steps) == (True, expected)
    latched, safe_steps = update_recovery_guard_latch(
        latched, safe_steps, 0.5, 0, 2.5, 1.0, 2, 3)
    assert (latched, safe_steps) == (False, 0)


def test_absolute_seam_limit_blends_and_allows_bounded_recovery():
    assert compute_seam_absolute_steer_limit(
        1.0, 0.10, 0.18, 0.18) == pytest.approx(0.10)
    assert compute_seam_absolute_steer_limit(
        0.5, 0.10, 0.18, 0.18) == pytest.approx(0.14)
    assert compute_seam_absolute_steer_limit(
        1.0, 0.10, 0.18, 0.12, True) == pytest.approx(0.12)
    assert compute_seam_absolute_steer_limit(
        0.0, 0.10, 0.18, 0.12, True) == pytest.approx(0.18)


def test_absolute_guard_blocks_outward_accumulation_without_snapback():
    assert limit_accumulated_steering(0.08, 0.14, 0.10) == pytest.approx(0.10)
    assert limit_accumulated_steering(0.20, 0.24, 0.18) == pytest.approx(0.20)
    assert limit_accumulated_steering(0.20, 0.16, 0.18) == pytest.approx(0.16)
    assert limit_accumulated_steering(-0.20, -0.24, 0.18) == pytest.approx(-0.20)
    assert limit_accumulated_steering(-0.20, -0.16, 0.18) == pytest.approx(-0.16)


def test_recovery_pd_target_points_toward_signed_gap_and_is_bounded():
    assert compute_recovery_steering_target(
        2.0, 1.0, 0.04, 0.01, 0.12) == pytest.approx(-0.09)
    assert compute_recovery_steering_target(
        -4.0, -2.0, 0.04, 0.01, 0.12) == pytest.approx(0.12)


def test_recovery_target_step_is_rate_limited():
    assert step_steering_toward_target(0.0, 0.12, 0.025) == pytest.approx(0.025)
    assert step_steering_toward_target(0.08, -0.12, 0.025) == pytest.approx(0.055)
    assert compute_recovery_guard_weight(
        gap_m=0.0,
        number_of_tyres_out=1,
        full_guard_gap_m=0.8,
        release_guard_gap_m=1.5,
    ) == pytest.approx(0.0)


def test_steering_rate_filter_passes_first_command_without_startup_lag():
    result = filter_steering_rate_command(
        steering_command=1.0,
        previous_filtered_command=0.0,
        alpha=0.8,
        initialized=False,
    )

    assert result == pytest.approx(1.0)


def test_steering_rate_filter_attenuates_high_frequency_reversal():
    result = filter_steering_rate_command(
        steering_command=-1.0,
        previous_filtered_command=1.0,
        alpha=0.8,
    )

    assert result == pytest.approx(-0.6)


@pytest.mark.parametrize("alpha", [0.0, -0.1, 1.1])
def test_steering_rate_filter_rejects_invalid_alpha(alpha):
    with pytest.raises(ValueError):
        filter_steering_rate_command(0.0, 0.0, alpha)
