"""Audit crossing-to-crossing laps from saved AC parquet telemetry.

Ignores the initial partial lap, persistent AC BestLap, and seeded lap times.
Outputs per-lap validity and distance-binned telemetry for experiment review.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def audit_laps(frame, track_length):
    distance = frame.LapDist.to_numpy(dtype=float) % track_length
    stamp = frame.timestamp_ac.to_numpy(dtype=float)
    crossings = np.flatnonzero(
        (distance[:-1] >= .8 * track_length)
        & (distance[1:] <= .2 * track_length)
        & (distance[:-1] - distance[1:] >= .5 * track_length)
    ) + 1
    crossing_times = []
    for i in crossings:
        span = track_length - distance[i - 1] + distance[i]
        fraction = (track_length - distance[i - 1]) / span
        crossing_times.append(stamp[i - 1] + fraction * (stamp[i] - stamp[i - 1]))
    laps = []
    for n, (start, end) in enumerate(zip(crossings[:-1], crossings[1:]), 1):
        lap = frame.iloc[start:end].copy()
        reasons = []
        # Include the ending crossing sample in validity checks, but exclude
        # it from distance-binned aggregates because it belongs to the next lap.
        checked = frame.iloc[start:end + 1]
        for channel, threshold in [("LapInvalidated", 0), ("penaltyTime", 0),
                                   ("numberOfTyresOut", 2), ("out_of_track", 0)]:
            if channel not in checked or checked[channel].isna().any():
                reasons.append("missing_" + channel)
            elif (checked[channel] > threshold).any():
                reasons.append(channel)
        lap_dt = np.diff(stamp[start - 1:end + 1])
        if not np.isfinite(lap_dt).all() or (lap_dt <= 0).any():
            reasons.append("non_monotonic_time")
        elapsed = crossing_times[n] - crossing_times[n - 1]
        if not np.isfinite(elapsed) or elapsed <= 0:
            reasons.append("invalid_elapsed")
        lap["dt"] = lap.timestamp_ac.diff().fillna(0)
        lap["bin_m"] = (lap.LapDist // 100).astype(int) * 100
        bins = []
        for position, section in lap.groupby("bin_m"):
            bins.append({
                "distance_m": int(position),
                "seconds": float(section.dt.sum()),
                "mean_speed_kmh": float(section.speed.mean() * 3.6),
                "min_speed_kmh": float(section.speed.min() * 3.6),
                "mean_abs_gap_m": float(section.gap.abs().mean()),
                "coast_s": float(section.loc[(section.accStatus < .1)
                                               & (section.brakeStatus < .05), "dt"].sum()),
                "pedal_overlap_s": float(section.loc[(section.accStatus > .2)
                                                       & (section.brakeStatus > .1), "dt"].sum()),
            })
        laps.append({
            "lap": n, "seconds": float(elapsed), "valid": not reasons,
            "invalid_reasons": reasons, "start_row": int(start), "end_row": int(end),
            "max_sample_gap_s": float(lap_dt.max()),
            "coast_s": sum(x["coast_s"] for x in bins),
            "pedal_overlap_s": sum(x["pedal_overlap_s"] for x in bins),
            "bins": bins,
        })
    return laps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    records = []
    for path in sorted(args.run_dir.glob("**/*_states.parquet")):
        static_path = path.parent / "static_info.json"
        if not static_path.exists():
            raise RuntimeError("Missing track metadata: " + str(static_path))
        length = float(json.loads(static_path.read_text(encoding="utf-8"))["TrackLength"])
        frame = pd.read_parquet(path)
        laps = audit_laps(frame, length)
        records.append({"telemetry": str(path.resolve()), "rows": len(frame),
                        "end_distance_m": float(frame.LapDist.iloc[-1]), "laps": laps})
    valid = [lap["seconds"] for record in records for lap in record["laps"] if lap["valid"]]
    result = {"episodes": len(records), "full_laps": sum(len(r["laps"]) for r in records),
              "valid_laps": len(valid), "best_valid_s": min(valid) if valid else None,
              "median_valid_s": float(np.median(valid)) if valid else None,
              "records": records}
    output = args.run_dir / "lap_audit.json"
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "records"}))


if __name__ == "__main__":
    main()
