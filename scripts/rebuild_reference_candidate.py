"""Boundary-constrained geometric route reconstruction (not minimum lap time).

Solve a sparse quadratic least-squares surrogate for curvature and its variation.
The candidate needs dynamic validation and a speed profile before promotion.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import lsq_linear
from scipy.interpolate import CubicSpline

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/rebuild_study_20261003/reference_lines"


def main():
    source = ROOT / "assetto_corsa_gym/AssettoCorsaConfigs/tracks/ks_silverstone-gp.csv"
    frame = pd.read_csv(source)
    original = frame[["pos_x", "pos_y"]].to_numpy()
    left = frame[["left_border_x", "left_border_y"]].to_numpy()
    right = frame[["right_border_x", "right_border_y"]].to_numpy()
    width = np.linalg.norm(right-left, axis=1)
    normal = (right-left)/width[:, None]
    center = (left+right)/2
    idx = np.arange(0, len(frame), 3)
    n = len(idx)
    # Periodic finite differences on roughly uniform ~4.5m cross sections.
    eye = sparse.eye(n, format="csr")
    shift = eye[np.roll(np.arange(n), -1)]
    d1 = shift-eye
    d2 = d1@d1
    d3 = d1@d2
    blocks, targets = [], []
    for derivative, weight in [(d2, 1.), (d3, 2.)]:
        for dim in range(2):
            blocks.append(weight*derivative@sparse.diags(normal[idx, dim]))
            targets.append(-weight*(derivative@center[idx, dim]))
    # Weak tie breaker toward the original route, not an imitation objective.
    old_offset = np.sum((original-center)*normal, axis=1)
    blocks.append(.01*eye)
    targets.append(.01*old_offset[idx])
    margin = 1.2  # Approximate vehicle half-width plus screening buffer.
    limits = width[idx]/2-margin
    if (limits <= 0).any():
        raise ValueError("Track cross section too narrow for chosen margin")
    A = sparse.vstack(blocks, format="csr")
    b = np.concatenate(targets)
    fit = lsq_linear(A, b, bounds=(-limits, limits), tol=1e-6,
                     lsmr_tol=1e-7, max_iter=100)
    if not fit.success:
        raise RuntimeError(f"Geometry optimization failed: {fit.message}")
    spline = CubicSpline(np.r_[idx, len(frame)], np.r_[fit.x, fit.x[0]], bc_type="periodic")
    offset = spline(np.arange(len(frame)))
    # Recheck bounds after interpolation at every recorded cross section.
    offset = np.clip(offset, -width/2+margin, width/2-margin)
    xy = center + offset[:, None]*normal
    steps = np.linalg.norm(np.roll(xy,-1,axis=0)-xy, axis=1)
    if not np.isfinite(xy).all() or steps.min()<.05 or steps.max()>5:
        raise RuntimeError("Invalid interpolated route geometry")
    # Reject paths that move backward relative to the source cross sections.
    forward = np.roll(center,-1,axis=0)-center
    if (np.sum((np.roll(xy,-1,axis=0)-xy)*forward,axis=1)<=0).any():
        raise RuntimeError("Route moves backward at a cross section")
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "boundary_rebuilt.csv"
    pd.DataFrame(xy, columns=["pos_x", "pos_y"]).to_csv(target,index=False)
    report = {
        "source":str(source), "output":str(target), "success":bool(fit.success),
        "cost":float(fit.cost), "iterations":int(fit.nit),
        "samples":len(xy), "optimization_variables":n, "cross_section_margin_m":margin,
        "max_displacement_from_old_m":float(np.linalg.norm(xy-original,axis=1).max()),
        "length_m":float(steps.sum()), "seam_step_m":float(steps[-1]),
        "max_step_m":float(steps.max()),
        "limitations":["geometric curvature surrogate, not minimum lap time",
                        "cross-section checks are not full vehicle swept-volume validation",
                        "no car-specific speed profile or dynamic feasibility proof yet",
                        "unproven observation-distribution shift for the existing policy"]}
    (OUT/"rebuild_audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
