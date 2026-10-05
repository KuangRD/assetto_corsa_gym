"""Configurable soft reference-line preference; track legality stays separate."""
import math


def reference_line_multiplier(gap, scale=12.0, corridor=0.0):
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("reference penalty scale must be finite and positive")
    if not math.isfinite(corridor) or corridor < 0:
        raise ValueError("reference corridor must be finite and nonnegative")
    # Exactly retains the historical reward when corridor=0 and scale=12.
    return 1.0 - max(0.0, abs(float(gap)) - corridor) / scale
