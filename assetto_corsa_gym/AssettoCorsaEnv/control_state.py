"""Small, simulator-independent checks for unsafe external control states."""


def has_low_speed_high_gear_conflict(
        actual_gear,
        speed_m_s,
        episode_step,
        *,
        minimum_invalid_gear=7,
        maximum_speed_m_s=30.0,
        maximum_episode_step=250):
    """Return whether a physical shifter is likely overriding auto-shift.

    Assetto Corsa reports neutral as 1 and forward gears above it, so the
    six-speed MX-5 reaches value 7 only in sixth.  Seeing that value below
    30 m/s immediately after the start is not a valid automatic-shift state.
    """
    try:
        gear = int(actual_gear)
        speed = float(speed_m_s)
        step = int(episode_step)
    except (TypeError, ValueError):
        return False

    return (
        gear >= int(minimum_invalid_gear)
        and speed <= float(maximum_speed_m_s)
        and 0 <= step <= int(maximum_episode_step)
    )
