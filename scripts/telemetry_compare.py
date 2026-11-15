"""Extract fastest valid laps and align AC telemetry on lap distance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

CHANNELS = [
    "distance_m", "lap_time_s", "speed_m_s", "throttle", "brake",
    "steer_deg", "gear", "rpm", "lat_accel_g", "long_accel_g",
    "lap_invalidated",
]


def _read(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path) if path.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(path)
    # MoTeC i2 CSV channel names also used by this repository's MotecLoader.
    aliases = {
        "session lap count": "LapCount", "car pos norm": "NormalizedSplinePosition",
        "lap time": "currentTime", "ground speed": "speed", "throttle pos": "accStatus",
        "brake pos": "brakeStatus", "steering angle": "steerAngle",
        "engine rpm": "RPM", "cg accel lateral": "accelX",
        "cg accel longitudinal": "accelY", "num tires off track": "numberOfTyresOut",
    }
    rename = {column: aliases[column.strip().lower()] for column in frame.columns if column.strip().lower() in aliases}
    frame = frame.rename(columns=rename)
    if "speed" in frame and "ground speed" in rename:
        frame["speed"] = pd.to_numeric(frame["speed"], errors="coerce") / 3.6
    for channel, source in (("accStatus", "throttle pos"), ("brakeStatus", "brake pos")):
        if channel in frame and source in rename:
            frame[channel] = pd.to_numeric(frame[channel], errors="coerce") / 100.0
    if "gear" in {c.lower() for c in frame.columns} and "actualGear" not in frame:
        gear_col = next(c for c in frame.columns if c.lower() == "gear")
        frame["actualGear"] = pd.to_numeric(frame[gear_col], errors="coerce") + 1
    return frame


def _first(frame: pd.DataFrame, *names: str, default=np.nan):
    for name in names:
        if name in frame:
            return frame[name]
    return pd.Series(default, index=frame.index)


def fastest_valid_lap(frame: pd.DataFrame, track_length: float) -> tuple[pd.DataFrame, float, int]:
    required = {"LapCount", "NormalizedSplinePosition"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing lap segmentation channels: {sorted(missing)}")
    time_col = next((c for c in ("timestamp_ac", "timestamp_env", "currentTime") if c in frame), None)
    if not time_col:
        raise ValueError("Need timestamp_ac, timestamp_env, or currentTime to time laps")
    candidates = []
    for lap_id, group in frame.groupby("LapCount", sort=False):
        group = group.copy()
        pos = pd.to_numeric(group.NormalizedSplinePosition, errors="coerce")
        if pos.notna().sum() < 10 or pos.max() - pos.min() < 0.80:
            continue
        if "LapInvalidated" in group and pd.to_numeric(group.LapInvalidated, errors="coerce").fillna(0).max() > 0:
            continue
        if "numberOfTyresOut" in group and pd.to_numeric(group.numberOfTyresOut, errors="coerce").max() >= 4:
            continue
        t = pd.to_numeric(group[time_col], errors="coerce")
        good = t.notna() & pos.notna()
        group, t, pos = group.loc[good], t.loc[good], pos.loc[good]
        if len(group) < 10:
            continue
        elapsed = float(t.iloc[-1] - t.iloc[0])
        if elapsed <= 0:
            continue
        # Keep a single monotonic lap traversal and use spline distance as the common axis.
        group = group.assign(_t=t.to_numpy(), distance_m=pos.to_numpy() * track_length)
        group = group.sort_values("_t").drop_duplicates("distance_m", keep="last")
        if group.distance_m.max() - group.distance_m.min() < track_length * 0.80:
            continue
        group["lap_time_s"] = group._t - group._t.iloc[0]
        candidates.append((elapsed, int(lap_id), group))
    if not candidates:
        raise ValueError("No complete, valid lap found. Check LapCount, spline position, and invalidation channels.")
    elapsed, lap_id, lap = min(candidates, key=lambda row: row[0])
    out = pd.DataFrame({
        "distance_m": lap.distance_m,
        "lap_time_s": lap.lap_time_s,
        "speed_m_s": _first(lap, "speed"),
        "throttle": _first(lap, "accStatus", "throttle"),
        "brake": _first(lap, "brakeStatus"),
        "steer_deg": _first(lap, "steerAngle", "steering angle"),
        "gear": _first(lap, "actualGear", "gear"),
        "rpm": _first(lap, "RPM", "rpm"),
        "lat_accel_g": _first(lap, "accelX"),
        "long_accel_g": _first(lap, "accelY"),
        "lap_invalidated": _first(lap, "LapInvalidated", default=0),
    })
    return out.sort_values("distance_m"), elapsed, lap_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="AC episode states Parquet or channel-mapped MoTeC CSV")
    parser.add_argument("--track-length", type=float, default=5891.0, help="Silverstone GP length in metres; override for other layouts")
    parser.add_argument("--driver", default="AI", help="Driver label written to metadata")
    parser.add_argument("--out", type=Path, help="Canonical lap CSV path (default: <source>_<driver>_best_lap.csv)")
    parser.add_argument("--compare", type=Path, help="Second canonical lap CSV; write a distance-aligned comparison")
    parser.add_argument("--step-m", type=float, default=5.0, help="Distance grid spacing for comparison")
    args = parser.parse_args()
    data = _read(args.source)
    lap, lap_time, lap_id = fastest_valid_lap(data, args.track_length)
    output = args.out or args.source.with_name(f"{args.source.stem}_{args.driver}_best_lap.csv")
    lap.to_csv(output, index=False)
    meta = {"source": str(args.source.resolve()), "driver": args.driver, "track_length_m": args.track_length,
            "lap_id": lap_id, "lap_time_s": lap_time, "distance_axis": "NormalizedSplinePosition * track_length_m",
            "channels": CHANNELS}
    output.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Best valid lap: {lap_time:.3f}s (LapCount={lap_id}); wrote {output}")
    if args.compare:
        other = pd.read_csv(args.compare)
        step = max(0.1, args.step_m)
        grid = np.arange(0, args.track_length + step / 2, step)
        result = pd.DataFrame({"distance_m": grid})
        for label, table in ((args.driver, lap), (args.compare.stem, other)):
            table = table.sort_values("distance_m").drop_duplicates("distance_m")
            for channel in CHANNELS[1:]:
                if channel not in table:
                    continue
                result[f"{label}_{channel}"] = np.interp(grid, table.distance_m, table[channel])
        # Delta time at a common distance is the principal pace comparison.
        time_columns = [c for c in result if c.endswith("_lap_time_s")]
        if len(time_columns) == 2:
            result["delta_time_s"] = result[time_columns[0]] - result[time_columns[1]]
        target = output.with_name(f"{output.stem}_comparison.csv")
        result.to_csv(target, index=False)
        print(f"Distance-aligned comparison: {target}")


if __name__ == "__main__":
    main()
