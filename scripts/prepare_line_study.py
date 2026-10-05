"""Build conservative reference candidates from independently audited full laps.

Geometry diagnostics are screening evidence, not proof of a faster racing line.
Track-boundary distances below use local recorded cross sections, not a polygon.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "outputs/line_setup_study_20261002"


def main():
    tracks = ROOT / "assetto_corsa_gym/AssettoCorsaConfigs/tracks"
    original = pd.read_csv(tracks / "ks_silverstone-gp-racing_line.csv")
    xy = original[["pos_x", "pos_y"]].to_numpy()
    borders = pd.read_csv(tracks / "ks_silverstone-gp.csv")
    assert len(borders) == len(xy)
    left = borders[["left_border_x", "left_border_y"]].to_numpy()
    right = borders[["right_border_x", "right_border_y"]].to_numpy()
    width = np.linalg.norm(right-left, axis=1)
    normal = (right-left)/width[:, None]
    distances = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    length = distances[-1]+np.linalg.norm(xy[-1]-xy[0])
    # Preserve the region with known controller intervention in this first test.
    taper = np.clip(np.minimum(distances, length-distances)/150-1, 0, 1)
    sources, trajectories = [], []
    for run in ["endurance_original", "endurance_original_repeat"]:
        audit = json.loads((ROOT / "outputs/speed_study_20261002" / run / "lap_audit.json").read_text())
        for record in audit["records"]:
            frame = pd.read_parquet(record["telemetry"])
            for lap in record["laps"]:
                if not lap["valid"]:
                    continue
                full = frame.iloc[lap["start_row"]:lap["end_row"]]
                positions = full[["world_position_x", "world_position_y"]].to_numpy()
                error, index = cKDTree(positions).query(xy)
                if error.max() > 12:
                    raise RuntimeError("Telemetry/reference alignment failed")
                trajectories.append(positions[index])
                sources.append({"telemetry": record["telemetry"], "lap":lap["lap"], "seconds":lap["seconds"]})
    median_delta = np.median(np.stack(trajectories)-xy, axis=0)
    candidates = {
        "periodic_smooth": gaussian_filter1d(xy, 2, axis=0, mode="wrap")-xy,
        "validated_trace_blend": .25*gaussian_filter1d(median_delta, 8, axis=0, mode="wrap"),
    }
    result = {"source_laps":sources, "note":"Candidates are unproven; taper preserves seam; lateral movement capped at0.5m; local-cross-section boundary screen only", "candidates":{}}
    for name, delta in candidates.items():
        # Lateral-only change avoids arbitrary phase shifts of the reference.
        lateral = np.clip(np.sum(delta*normal, axis=1), -.5, .5)*taper
        candidate = xy + lateral[:, None]*normal
        projected = np.sum((candidate-left)*normal, axis=1)
        clearance = np.minimum(projected, width-projected)
        unsafe = clearance < 1.0
        candidate[unsafe] = xy[unsafe]
        assert np.isfinite(candidate).all()
        step = np.linalg.norm(np.roll(candidate,-1,axis=0)-candidate,axis=1)
        assert step.min() > .01 and step.max() < 3
        path = STUDY / "reference_lines" / (name+".csv")
        pd.DataFrame(candidate,columns=["pos_x","pos_y"]).to_csv(path,index=False)
        result["candidates"][name] = {"file":str(path),"max_displacement_m":float(np.linalg.norm(candidate-xy,axis=1).max()),"median_spacing_m":float(np.median(step)),"max_spacing_m":float(step.max()),"seam_spacing_m":float(step[-1]),"boundary_fallback_points":int(unsafe.sum())}
    (STUDY / "reference_lines/geometry_audit.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result["candidates"],indent=2))


if __name__ == "__main__":
    main()
