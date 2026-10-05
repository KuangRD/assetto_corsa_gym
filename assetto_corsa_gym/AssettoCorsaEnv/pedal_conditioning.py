"""Optional, bounded pedal-overlap ablation; disabled by default."""

import math


def reduce_light_brake_overlap(throttle_command, brake_command, strength):
    """Reduce light brake axis input only near full throttle.

    Commands use [-1, 1]. These are controller axes, not game brake pressure
    (which additionally depends on AC's configured brake gamma). Preserve
    heavy braking, coasting and throttle. Smooth gates avoid threshold jumps.
    """
    strength = float(strength)
    if not math.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("pedal_overlap_reduction must be finite and in [0, 1]")
    if strength == 0:
        return brake_command
    throttle = min(1., max(0., (float(throttle_command) + 1.) / 2.))
    brake = min(1., max(0., (float(brake_command) + 1.) / 2.))
    throttle_gate = min(1., max(0., (throttle - .8) / .2))
    light_brake_gate = min(1., max(0., (.65 - brake) / .2))
    return 2. * brake * (1. - strength * throttle_gate * light_brake_gate) - 1.
