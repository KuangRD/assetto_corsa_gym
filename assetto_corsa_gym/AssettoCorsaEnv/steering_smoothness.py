"""Pure reward calculations for steering-smoothness training."""

import numpy as np


def compute_schedule_ramp(training_step, ramp_start_step, ramp_steps):
    """Return a zero-to-one linear schedule value."""
    if ramp_steps <= 0:
        return float(int(training_step) >= int(ramp_start_step))
    return float(np.clip(
        (int(training_step) - int(ramp_start_step)) / float(ramp_steps),
        0.0,
        1.0,
    ))


def compute_straight_gate(
        speed_m_s,
        gap_m,
        max_abs_curvature,
        *,
        min_speed_m_s,
        full_speed_m_s,
        curvature_threshold,
        max_gap_m):
    """Return a soft gate for fast, straight, near-racing-line states."""
    if full_speed_m_s <= min_speed_m_s:
        raise ValueError("full_speed_m_s must be greater than min_speed_m_s")
    if curvature_threshold <= 0 or max_gap_m <= 0:
        raise ValueError("straight gate thresholds must be positive")

    speed_weight = np.clip(
        (float(speed_m_s) - min_speed_m_s) /
        (full_speed_m_s - min_speed_m_s),
        0.0,
        1.0,
    )
    curvature_weight = np.clip(
        1.0 - abs(float(max_abs_curvature)) / curvature_threshold,
        0.0,
        1.0,
    )
    gap_weight = np.clip(1.0 - abs(float(gap_m)) / max_gap_m, 0.0, 1.0)
    return float(speed_weight * curvature_weight * gap_weight)


def compute_effective_steer_rate_limit(
        base_rate_deg_s,
        straight_rate_deg_s,
        straight_gate,
        ramp):
    """Blend from the normal steering limit to a straight-line limit."""
    base_rate_deg_s = float(base_rate_deg_s)
    straight_rate_deg_s = float(straight_rate_deg_s)
    if base_rate_deg_s <= 0 or straight_rate_deg_s <= 0:
        raise ValueError("steering rate limits must be positive")
    if straight_rate_deg_s > base_rate_deg_s:
        raise ValueError("straight steering rate limit cannot exceed base limit")
    blend = float(np.clip(straight_gate, 0.0, 1.0)) * float(
        np.clip(ramp, 0.0, 1.0))
    return base_rate_deg_s + blend * (straight_rate_deg_s - base_rate_deg_s)


def compute_periodic_seam_weight(
        distance_m,
        track_length_m,
        full_guard_distance_m,
        fade_guard_distance_m):
    """Return a continuous guard weight on both sides of start/finish."""
    track_length_m = float(track_length_m)
    full_guard_distance_m = float(full_guard_distance_m)
    fade_guard_distance_m = float(fade_guard_distance_m)
    if track_length_m <= 0:
        raise ValueError("track_length_m must be positive")
    if full_guard_distance_m < 0:
        raise ValueError("full_guard_distance_m cannot be negative")
    if fade_guard_distance_m <= full_guard_distance_m:
        raise ValueError(
            "fade_guard_distance_m must exceed full_guard_distance_m")
    wrapped = float(distance_m) % track_length_m
    distance_to_seam = min(wrapped, track_length_m - wrapped)
    return float(np.clip(
        (fade_guard_distance_m - distance_to_seam) /
        (fade_guard_distance_m - full_guard_distance_m),
        0.0,
        1.0,
    ))


def compute_post_seam_weight(
        distance_m,
        track_length_m,
        full_guard_distance_m,
        fade_guard_distance_m):
    """Return a one-sided guard weight only after start/finish."""
    track_length_m = float(track_length_m)
    full_guard_distance_m = float(full_guard_distance_m)
    fade_guard_distance_m = float(fade_guard_distance_m)
    if track_length_m <= 0:
        raise ValueError("track_length_m must be positive")
    if full_guard_distance_m < 0:
        raise ValueError("full_guard_distance_m cannot be negative")
    if fade_guard_distance_m <= full_guard_distance_m:
        raise ValueError(
            "fade_guard_distance_m must exceed full_guard_distance_m")
    wrapped = float(distance_m) % track_length_m
    return float(np.clip(
        (fade_guard_distance_m - wrapped) /
        (fade_guard_distance_m - full_guard_distance_m),
        0.0,
        1.0,
    ))


def extend_latched_recovery_weight(
        normal_weight, emergency_weight, recovery_latched):
    """Keep recovery authority past the normal handoff only when needed."""
    normal_weight = float(np.clip(normal_weight, 0.0, 1.0))
    emergency_weight = float(np.clip(emergency_weight, 0.0, 1.0))
    if not recovery_latched:
        return normal_weight
    return max(normal_weight, emergency_weight)


def compute_distance_zone_weight(
        distance_m,
        fade_in_start_m,
        full_start_m,
        full_end_m,
        fade_out_end_m):
    """Return a trapezoidal weight for one non-wrapping track interval."""
    fade_in_start_m = float(fade_in_start_m)
    full_start_m = float(full_start_m)
    full_end_m = float(full_end_m)
    fade_out_end_m = float(fade_out_end_m)
    if not (0 <= fade_in_start_m < full_start_m
            < full_end_m < fade_out_end_m):
        raise ValueError(
            "distance zone must satisfy 0 <= fade_in_start < full_start "
            "< full_end < fade_out_end")

    distance_m = float(distance_m)
    if distance_m <= fade_in_start_m or distance_m >= fade_out_end_m:
        return 0.0
    if full_start_m <= distance_m <= full_end_m:
        return 1.0
    if distance_m < full_start_m:
        return float(
            (distance_m - fade_in_start_m) /
            (full_start_m - fade_in_start_m))
    return float(
        (fade_out_end_m - distance_m) /
        (fade_out_end_m - full_end_m))


def compute_recovery_guard_weight(
        gap_m,
        number_of_tyres_out,
        full_guard_gap_m,
        release_guard_gap_m,
        disable_with_tyres_out=True,
        min_tyres_out_for_release=1):
    """Release steering protection when the car needs recovery authority."""
    full_guard_gap_m = float(full_guard_gap_m)
    release_guard_gap_m = float(release_guard_gap_m)
    if full_guard_gap_m < 0:
        raise ValueError("full_guard_gap_m cannot be negative")
    if release_guard_gap_m <= full_guard_gap_m:
        raise ValueError(
            "release_guard_gap_m must exceed full_guard_gap_m")
    min_tyres_out_for_release = int(min_tyres_out_for_release)
    if min_tyres_out_for_release < 1:
        raise ValueError("min_tyres_out_for_release must be at least one")
    if (disable_with_tyres_out
            and int(number_of_tyres_out) >= min_tyres_out_for_release):
        return 0.0
    abs_gap = abs(float(gap_m))
    return float(np.clip(
        (release_guard_gap_m - abs_gap) /
        (release_guard_gap_m - full_guard_gap_m),
        0.0,
        1.0,
    ))


def update_recovery_guard_latch(
        latched,
        safe_steps,
        gap_m,
        number_of_tyres_out,
        enter_gap_m,
        exit_gap_m,
        min_tyres_out_for_release,
        exit_hold_steps,
        enable_tyre_trigger=True):
    """Latch recovery authority until the car is stably back on line."""
    enter_gap_m = float(enter_gap_m)
    exit_gap_m = float(exit_gap_m)
    min_tyres_out_for_release = int(min_tyres_out_for_release)
    exit_hold_steps = int(exit_hold_steps)
    if enter_gap_m <= 0:
        raise ValueError("enter_gap_m must be positive")
    if not 0 <= exit_gap_m < enter_gap_m:
        raise ValueError("exit_gap_m must be in [0, enter_gap_m)")
    if min_tyres_out_for_release < 1:
        raise ValueError("min_tyres_out_for_release must be at least one")
    if exit_hold_steps < 1:
        raise ValueError("exit_hold_steps must be at least one")

    tyres_out = int(number_of_tyres_out)
    recovery_triggered = abs(float(gap_m)) >= enter_gap_m
    if enable_tyre_trigger:
        recovery_triggered = (
            recovery_triggered
            or tyres_out >= min_tyres_out_for_release)
    if not bool(latched):
        return (True, 0) if recovery_triggered else (False, 0)

    stable = abs(float(gap_m)) <= exit_gap_m and tyres_out == 0
    next_safe_steps = int(safe_steps) + 1 if stable else 0
    if next_safe_steps >= exit_hold_steps:
        return False, 0
    return True, next_safe_steps


def compute_seam_absolute_steer_limit(
        seam_position_weight,
        full_zone_limit,
        fade_edge_limit,
        recovery_limit,
        recovery_latched=False):
    """Return an absolute steering-control envelope near the seam."""
    full_zone_limit = float(full_zone_limit)
    fade_edge_limit = float(fade_edge_limit)
    recovery_limit = float(recovery_limit)
    if not 0 < full_zone_limit <= fade_edge_limit <= 1:
        raise ValueError(
            "absolute steer limits must satisfy 0 < full <= fade <= 1")
    if not full_zone_limit <= recovery_limit <= 1:
        raise ValueError(
            "recovery_limit must be between full_zone_limit and one")
    position_weight = float(np.clip(seam_position_weight, 0.0, 1.0))
    limit = full_zone_limit + (
        1.0 - position_weight) * (fade_edge_limit - full_zone_limit)
    if recovery_latched:
        # Recovery needs at least ``recovery_limit`` authority, while the
        # normal fade may already allow more.  Never tighten the envelope
        # again while leaving the protected zone.
        limit = max(limit, recovery_limit)
    return float(limit)


def limit_accumulated_steering(
        current_absolute_steering,
        proposed_absolute_steering,
        max_absolute_steering):
    """Prevent outward accumulation without snapping an over-limit wheel."""
    current = float(current_absolute_steering)
    proposed = float(proposed_absolute_steering)
    limit = float(max_absolute_steering)
    if not 0 < limit <= 1:
        raise ValueError("max_absolute_steering must be in (0, 1]")
    if current > limit:
        return float(min(proposed, current))
    if current < -limit:
        return float(max(proposed, current))
    return float(np.clip(proposed, -limit, limit))


def compute_recovery_steering_target(
        gap_m,
        gap_rate_m_s,
        proportional_gain,
        derivative_gain,
        max_absolute_steering):
    """Return a bounded absolute steering target toward the reference line."""
    proportional_gain = float(proportional_gain)
    derivative_gain = float(derivative_gain)
    limit = float(max_absolute_steering)
    if proportional_gain < 0 or derivative_gain < 0:
        raise ValueError("recovery steering gains cannot be negative")
    if not 0 < limit <= 1:
        raise ValueError("max_absolute_steering must be in (0, 1]")
    return float(np.clip(
        -(proportional_gain * float(gap_m)
          + derivative_gain * float(gap_rate_m_s)),
        -limit,
        limit,
    ))


def step_steering_toward_target(
        current_absolute_steering,
        target_absolute_steering,
        max_delta):
    """Move an absolute steering command toward a target without jumping."""
    max_delta = float(max_delta)
    if max_delta <= 0:
        raise ValueError("max_delta must be positive")
    current = float(current_absolute_steering)
    target = float(target_absolute_steering)
    return float(np.clip(target, current - max_delta, current + max_delta))


def condition_seam_steering_command(
        steering_command,
        previous_conditioned_command,
        seam_weight,
        max_abs_command,
        reversal_damping):
    """Clamp seam steering deltas and damp reversals without direction lag.

    Relative steering actions are increments, not absolute targets. Low-pass
    filtering them can therefore keep applying the old direction after the
    policy reverses. A reversal is attenuated here but takes effect in the
    requested direction immediately.
    """
    max_abs_command = float(max_abs_command)
    reversal_damping = float(reversal_damping)
    if not 0 < max_abs_command <= 1:
        raise ValueError("max_abs_command must be in (0, 1]")
    if not 0 < reversal_damping <= 1:
        raise ValueError("reversal_damping must be in (0, 1]")
    weight = float(np.clip(seam_weight, 0.0, 1.0))
    command = float(np.clip(steering_command, -1.0, 1.0))
    previous = float(np.clip(previous_conditioned_command, -1.0, 1.0))
    guarded = float(np.clip(command, -max_abs_command, max_abs_command))
    if guarded * previous < 0.0:
        guarded *= reversal_damping
    return float(np.clip(command + weight * (guarded - command), -1.0, 1.0))


def condition_strong_steering_reversal(
        steering_command,
        previous_policy_command,
        reversal_damping,
        minimum_reversal_magnitude):
    """Attenuate a strong reversal while following its direction immediately.

    Detection uses consecutive unconditioned policy commands. This avoids an
    alternating command escaping the guard merely because the previous
    executed command was already attenuated.
    """
    reversal_damping = float(reversal_damping)
    minimum_reversal_magnitude = float(minimum_reversal_magnitude)
    if not 0 < reversal_damping <= 1:
        raise ValueError("reversal_damping must be in (0, 1]")
    if not 0 <= minimum_reversal_magnitude <= 1:
        raise ValueError(
            "minimum_reversal_magnitude must be in [0, 1]")
    command = float(np.clip(steering_command, -1.0, 1.0))
    previous = float(np.clip(previous_policy_command, -1.0, 1.0))
    strong_reversal = (
        command * previous < 0.0
        and min(abs(command), abs(previous)) >= minimum_reversal_magnitude
    )
    if strong_reversal:
        command *= reversal_damping
    return command


def filter_steering_rate_command(
        steering_command,
        previous_filtered_command,
        alpha,
        initialized=True):
    """Low-pass a relative steering-rate command without changing its limits."""
    alpha = float(alpha)
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    command = float(np.clip(steering_command, -1.0, 1.0))
    if not initialized:
        return command
    previous = float(np.clip(previous_filtered_command, -1.0, 1.0))
    return float(np.clip(
        alpha * command + (1.0 - alpha) * previous,
        -1.0,
        1.0,
    ))


def condition_steering_guards(
        steering_command,
        previous_policy_command,
        previous_conditioned_command,
        seam_weight,
        seam_max_abs_command,
        seam_reversal_damping,
        enable_global_reversal_guard,
        global_reversal_damping,
        global_minimum_reversal_magnitude):
    """Route one command to the seam guard or the global reversal guard."""
    if float(seam_weight) > 0.0:
        return (
            condition_seam_steering_command(
                steering_command,
                previous_conditioned_command,
                seam_weight,
                seam_max_abs_command,
                seam_reversal_damping,
            ),
            False,
        )
    if enable_global_reversal_guard:
        guarded = condition_strong_steering_reversal(
            steering_command,
            previous_policy_command,
            global_reversal_damping,
            global_minimum_reversal_magnitude,
        )
        return guarded, not np.isclose(guarded, steering_command)
    return float(np.clip(steering_command, -1.0, 1.0)), False


def compute_steering_smoothness_terms(
        steering_command,
        previous_steering_command,
        steering_rate_deg_s,
        speed_m_s,
        gap_m,
        max_abs_curvature,
        training_step,
        *,
        command_coef,
        reversal_coef,
        rate_coef,
        max_steer_rate_deg_s,
        min_speed_m_s,
        full_speed_m_s,
        curvature_threshold,
        max_gap_m,
        ramp_start_step,
        ramp_steps,
        previous_previous_steering_command=None,
        straight_gate_floor=0.0,
        jerk_coef=0.0,
        global_reversal_coef=0.0,
        global_jerk_coef=0.0,
        global_chatter_coef=0.0):
    """Return gated steering-smoothness reward terms for one transition.

    The gate concentrates the penalty on high-speed, low-curvature states near
    the reference line. This keeps the regular racing reward responsible for
    recovery manoeuvres and necessary steering in corners.
    """
    if max_steer_rate_deg_s <= 0:
        raise ValueError("max_steer_rate_deg_s must be positive")

    straight_gate = compute_straight_gate(
        speed_m_s=speed_m_s,
        gap_m=gap_m,
        max_abs_curvature=max_abs_curvature,
        min_speed_m_s=min_speed_m_s,
        full_speed_m_s=full_speed_m_s,
        curvature_threshold=curvature_threshold,
        max_gap_m=max_gap_m,
    )
    straight_gate = max(
        straight_gate,
        float(np.clip(straight_gate_floor, 0.0, 1.0)),
    )
    ramp = compute_schedule_ramp(training_step, ramp_start_step, ramp_steps)
    effective_gate = straight_gate * ramp

    command = float(np.clip(steering_command, -1.0, 1.0))
    previous_command = float(np.clip(previous_steering_command, -1.0, 1.0))
    if previous_previous_steering_command is None:
        previous_previous_command = previous_command
    else:
        previous_previous_command = float(np.clip(
            previous_previous_steering_command, -1.0, 1.0))
    normalized_rate = float(np.clip(
        abs(float(steering_rate_deg_s)) / max_steer_rate_deg_s,
        0.0,
        1.0,
    ))

    # A positive product after negating means the command changed sign. Its
    # magnitude is high only for strong left/right reversals.
    reversal_strength = max(0.0, -command * previous_command)
    # The relative steering command represents desired steering velocity. Its
    # step-to-step change is therefore steering acceleration (jerk-like input).
    # Dividing by two normalizes the largest possible -1 -> +1 jump to one.
    jerk_strength = ((command - previous_command) / 2.0) ** 2
    # A single direction change is often a legitimate corner correction. A
    # second immediate change back forms a three-frame chatter pattern and is
    # the behavior that should be penalized across the whole track.
    is_chatter = (
        command * previous_command < 0.0
        and previous_command * previous_previous_command < 0.0
    )
    chatter_strength = 0.0
    if is_chatter:
        chatter_strength = min(
            abs(command),
            abs(previous_command),
            abs(previous_previous_command),
        ) ** 2
    # Sustained steering magnitude and physical steering rate are penalized
    # only on straights, where they are usually unnecessary. High-frequency
    # reversal and jerk terms also have a curvature-independent component so
    # corner oscillation is discouraged without penalizing a stable turn.
    command_penalty = effective_gate * command_coef * command ** 2
    straight_reversal_penalty = (
        effective_gate * reversal_coef * reversal_strength)
    global_reversal_penalty = (
        ramp * global_reversal_coef * reversal_strength)
    reversal_penalty = straight_reversal_penalty + global_reversal_penalty
    rate_penalty = effective_gate * rate_coef * normalized_rate ** 2
    straight_jerk_penalty = effective_gate * jerk_coef * jerk_strength
    global_jerk_penalty = ramp * global_jerk_coef * jerk_strength
    jerk_penalty = straight_jerk_penalty + global_jerk_penalty
    chatter_penalty = ramp * global_chatter_coef * chatter_strength

    return {
        "straight_gate": straight_gate,
        "ramp": ramp,
        "effective_gate": effective_gate,
        "steering_rate_deg_s": abs(float(steering_rate_deg_s)),
        "command_penalty": float(command_penalty),
        "straight_reversal_penalty": float(straight_reversal_penalty),
        "global_reversal_penalty": float(global_reversal_penalty),
        "reversal_penalty": float(reversal_penalty),
        "rate_penalty": float(rate_penalty),
        "straight_jerk_penalty": float(straight_jerk_penalty),
        "global_jerk_penalty": float(global_jerk_penalty),
        "jerk_penalty": float(jerk_penalty),
        "chatter_strength": float(chatter_strength),
        "chatter_penalty": float(chatter_penalty),
        "total_penalty": float(
            command_penalty + reversal_penalty + rate_penalty + jerk_penalty
            + chatter_penalty),
    }
