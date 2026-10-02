"""Summarize repeatable steering chatter by lap-distance bins in AC telemetry."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def _signed_reversals(values: np.ndarray, magnitude: float = 0.15) -> int:
    values = np.asarray(values, dtype=float)
    if values.size < 2:
        return 0
    return int(np.sum((values[:-1] * values[1:] < 0.0) & (np.abs(values[:-1]) >= magnitude) & (np.abs(values[1:]) >= magnitude)))


def summarize(path: Path, bin_width: float) -> pd.DataFrame:
    df = pd.read_parquet(path)
    required = {"LapDist", "LapCount", "speed", "steerAngle", "actions_0"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")

    work = df.copy()
    work["distance_bin"] = np.floor(work["LapDist"] / bin_width) * bin_width
    work["abs_action"] = work["actions_0"].abs()
    work["abs_policy_action"] = work.get("policy_actions_0", work["actions_0"]).abs()
    work["abs_steer_control"] = work.get("current_action_abs_0", 0.0)
    work["abs_steer_control"] = work["abs_steer_control"].abs()
    work["abs_steer"] = work["steerAngle"].abs()
    work["steer_step"] = work.groupby("LapCount", sort=False)["steerAngle"].diff().abs()

    rows = []
    for (lap, start), part in work.groupby(["LapCount", "distance_bin"], sort=True):
        rows.append(
            {
                "lap": int(lap),
                "start_m": int(start),
                "end_m": int(start + bin_width),
                "samples": len(part),
                "speed_mean": part["speed"].mean(),
                "speed_min": part["speed"].min(),
                "speed_max": part["speed"].max(),
                "action_p95": part["abs_action"].quantile(0.95),
                "action_max": part["abs_action"].max(),
                "policy_action_p95": part["abs_policy_action"].quantile(0.95),
                "reversals": _signed_reversals(part["actions_0"].to_numpy()),
                "steer_control_p95": part["abs_steer_control"].quantile(0.95),
                "steer_abs_p95": part["abs_steer"].quantile(0.95),
                "steer_step_p95": part["steer_step"].quantile(0.95),
                "gap_abs_max": part["gap"].abs().max() if "gap" in part else np.nan,
                "tyres_out_max": part["numberOfTyresOut"].max() if "numberOfTyresOut" in part else np.nan,
                "smooth_gate_mean": part["steer_smooth_gate"].mean() if "steer_smooth_gate" in part else np.nan,
                "guard_mean": part["seam_absolute_position_weight"].mean() if "seam_absolute_position_weight" in part else np.nan,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--bin-width", type=float, default=100.0)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=6000.0)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    all_rows = []
    for path in args.paths:
        rows = summarize(path, args.bin_width)
        rows.insert(0, "file", path.name)
        all_rows.append(rows)
    result = pd.concat(all_rows, ignore_index=True)
    result = result[(result["start_m"] >= args.start) & (result["start_m"] < args.end)]

    display_cols = [
        "file", "lap", "start_m", "end_m", "samples", "speed_mean", "speed_min", "speed_max",
        "action_p95", "action_max", "policy_action_p95", "reversals",
        "steer_control_p95", "steer_abs_p95", "steer_step_p95",
        "gap_abs_max", "tyres_out_max", "smooth_gate_mean", "guard_mean",
    ]
    print("DISTANCE RANGE")
    print(result[display_cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nTOP CHATTER BINS")
    top = result.sort_values(["reversals", "action_p95", "steer_step_p95"], ascending=False).head(args.top)
    print(top[display_cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
