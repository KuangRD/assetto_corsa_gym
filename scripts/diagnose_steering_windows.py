"""Screen audited laps for repeated steering motion without assigning causality."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.signal import find_peaks


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("run",type=Path)
    args=parser.parse_args()
    audit=json.loads((args.run/"lap_audit.json").read_text())
    windows=[]
    for record in audit["records"]:
        frame=pd.read_parquet(record["telemetry"])
        for lap in record["laps"]:
            if not lap["valid"]:
                continue
            for start in range(lap["start_row"],lap["end_row"]-50,50):
                w=frame.iloc[start:start+50]
                t=w.timestamp_ac.to_numpy()
                if (np.diff(t)<=0).any() or np.diff(t).max()>.1:
                    continue
                steer=w.steerAngle.to_numpy()
                peaks,_=find_peaks(steer,prominence=5)
                troughs,_=find_peaks(-steer,prominence=5)
                span=float(np.ptp(steer))
                ratio=float(abs(np.diff(steer)).sum()/max(span,1.))
                windows.append({
                    "source":record["telemetry"],"start_row":start,"lap":lap["lap"],
                    "distance_m":float(w.LapDist.mean()),"speed_kmh":float(w.speed.mean()*3.6),
                    "steer_span_raw":span,"variation_to_span":ratio,
                    "prominent_extrema":len(peaks)+len(troughs),
                    "repeated_motion_screen":bool(span>=10 and ratio>=3 and len(peaks)+len(troughs)>=4),
                    "straight_gate":float(w.steer_smooth_gate.mean()),
                    "policy_executed_delta_mae":float(np.mean(abs(w.policy_actions_0-w.actions_0))),
                    "gap_start_abs":float(abs(w.gap.iloc[0])),"gap_end_abs":float(abs(w.gap.iloc[-1])),
                    "policy_sign_flips":int(np.sum(np.diff(np.sign(w.policy_actions_0))!=0)),
                    "executed_sign_flips":int(np.sum(np.diff(np.sign(w.actions_0))!=0)),
                })
    screened=[w for w in windows if w["repeated_motion_screen"]]
    report={"valid_laps":audit["valid_laps"],"nonoverlapping_windows":len(windows),
            "repeated_motion_windows":len(screened),
            "method":"50 samples/window;actual steer span>=10 raw units,variation/span>=3,at least4 extrema withprominence5;straight usesexistinggate. Screening only,not proof unnecessarymotion. Policy/executed actions are normalized relative increments. MAE includes filters and rate normalization,not solelyPD.",
            "top_windows":sorted(screened,key=lambda w:w["variation_to_span"],reverse=True)[:30]}
    (args.run/"steering_windows.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    if screened:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        pick=max(screened,key=lambda w:w["variation_to_span"])
        f=pd.read_parquet(pick["source"]).iloc[pick["start_row"]:pick["start_row"]+50]
        t=f.timestamp_ac-f.timestamp_ac.iloc[0]
        fig,ax=plt.subplots(3,1,figsize=(10,7),sharex=True)
        ax[0].plot(t,f.policy_actions_0,label="Policy relative command")
        ax[0].plot(t,f.actions_0,label="Executed relative command",alpha=.8)
        ax[0].legend();ax[0].set_ylabel("Relative command")
        ax[1].plot(t,f.steerAngle);ax[1].set_ylabel("Actual steer (raw)")
        ax[2].plot(t,f.gap);ax[2].set_ylabel("Reference gap (m)");ax[2].set_xlabel("Simulation time (s)")
        fig.suptitle(f"Repeated-motion screening window at {pick['distance_m']:.0f}m; not causal proof")
        fig.tight_layout();fig.savefig(args.run/"steering_window.png",dpi=140);plt.close(fig)
    print(json.dumps({k:v for k,v in report.items() if k not in ['top_windows','method']}))


if __name__=="__main__":
    main()
