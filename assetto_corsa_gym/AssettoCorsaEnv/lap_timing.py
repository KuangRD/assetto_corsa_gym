"""Lap timing based on physical start/finish crossings.

Assetto Corsa can preserve ``LapCount``, ``currentTime`` and ``iLastTime``
across a car reset.  A reset in the middle of a lap can consequently make the
next reported lap span two physical laps.  This module deliberately uses the
periodic track position and a monotonic simulator timestamp instead.
"""

from math import isfinite


def state_timestamp(state):
    """Return the best monotonic timestamp available in an environment state."""
    for key in ("timestamp_ac", "timestamp_env"):
        try:
            value = float(state[key])
        except (KeyError, TypeError, ValueError):
            continue
        if isfinite(value):
            return value
    raise ValueError("state has no finite timestamp_ac or timestamp_env")


class PhysicalLapTimer:
    """Measure complete laps from forward wraps of periodic lap distance."""

    def __init__(self, track_length, start_zone_fraction=0.01,
                 start_zone_max_m=10.0):
        self.track_length = float(track_length)
        if not isfinite(self.track_length) or self.track_length <= 0:
            raise ValueError("track_length must be positive and finite")
        self.start_zone_distance = min(
            self.track_length * float(start_zone_fraction),
            float(start_zone_max_m),
        )
        self._previous_distance = None
        self._previous_timestamp = None
        self._last_crossing_timestamp = None
        self._seeded_from_episode_start = False

    def reset(self, lap_distance, timestamp):
        """Start an episode, discarding a partial out-lap after a mid-lap reset."""
        distance = float(lap_distance) % self.track_length
        timestamp = float(timestamp)
        if not isfinite(timestamp):
            raise ValueError("timestamp must be finite")
        self._previous_distance = distance
        self._previous_timestamp = timestamp
        self._last_crossing_timestamp = (
            timestamp if distance <= self.start_zone_distance else None)
        self._seeded_from_episode_start = (
            self._last_crossing_timestamp is not None)

    def reset_state(self, state):
        self.reset(state["LapDist"], state_timestamp(state))

    def update(self, lap_distance, timestamp):
        """Return a completed physical lap time, or ``None`` without a crossing."""
        if self._previous_distance is None:
            self.reset(lap_distance, timestamp)
            return None

        distance = float(lap_distance) % self.track_length
        timestamp = float(timestamp)
        if not isfinite(timestamp):
            raise ValueError("timestamp must be finite")

        previous_distance = self._previous_distance
        previous_timestamp = self._previous_timestamp
        crossed = (
            previous_distance >= 0.8 * self.track_length
            and distance <= 0.2 * self.track_length
            and previous_distance - distance >= 0.5 * self.track_length
        )
        lap_time = None
        if crossed:
            remaining = self.track_length - previous_distance
            crossing_span = remaining + distance
            fraction = remaining / crossing_span if crossing_span > 0 else 1.0
            if self._seeded_from_episode_start:
                # Compare like-for-like sampled positions for the first lap.
                # The reset state is near, but not exactly on, the timing line.
                crossing_timestamp = timestamp
            else:
                crossing_timestamp = previous_timestamp + fraction * (
                    timestamp - previous_timestamp)
            if self._last_crossing_timestamp is not None:
                measured = crossing_timestamp - self._last_crossing_timestamp
                if isfinite(measured) and measured > 0:
                    lap_time = measured
            self._last_crossing_timestamp = crossing_timestamp
            self._seeded_from_episode_start = False

        self._previous_distance = distance
        self._previous_timestamp = timestamp
        return lap_time

    def update_state(self, state):
        return self.update(state["LapDist"], state_timestamp(state))


def physical_lap_times(states, track_length):
    """Extract complete, reset-local lap times from an iterable of states."""
    states = list(states)
    if not states:
        return []
    timer = PhysicalLapTimer(track_length)
    timer.reset_state(states[0])
    lap_times = []
    for state in states[1:]:
        lap_time = timer.update_state(state)
        if lap_time is not None:
            lap_times.append(lap_time)
    return lap_times
