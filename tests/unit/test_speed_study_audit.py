import importlib.util
from pathlib import Path

import pandas as pd


spec = importlib.util.spec_from_file_location(
    "speed_study", Path(__file__).resolve().parents[2] / "scripts/analyze_speed_study.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def frame():
    return pd.DataFrame({
        "LapDist": [500, 900, 0, 250, 500, 750, 900, 0],
        "timestamp_ac": [0, 4, 5, 7.5, 10, 12.5, 14, 15],
        "LapInvalidated": [0] * 8, "penaltyTime": [0] * 8,
        "numberOfTyresOut": [0] * 8, "out_of_track": [0] * 8,
        "speed": [100] * 8, "gap": [0] * 8,
        "accStatus": [1] * 8, "brakeStatus": [0] * 8,
    })


def test_ignores_outlap_and_session_best():
    data = frame()
    data["BestLap"] = 1
    laps = audit.audit_laps(data, 1000)
    assert len(laps) == 1
    assert laps[0]["seconds"] == 10
    assert laps[0]["valid"]


def test_rejects_invalidation_at_end_crossing():
    data = frame()
    data.loc[7, "LapInvalidated"] = 1
    lap = audit.audit_laps(data, 1000)[0]
    assert not lap["valid"]
    assert "LapInvalidated" in lap["invalid_reasons"]


def test_missing_validity_is_not_assumed_valid():
    lap = audit.audit_laps(frame().drop(columns="penaltyTime"), 1000)[0]
    assert not lap["valid"]
    assert "missing_penaltyTime" in lap["invalid_reasons"]
