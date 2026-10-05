"""Report completed independent evaluations, never mixed training trajectories."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "outputs/line_setup_study_20261002"


def main():
    rows = []
    for audit_path in sorted(STUDY.glob("*/lap_audit.json")):
        run = audit_path.parent
        if "train" in run.name:
            continue
        audit = json.loads(audit_path.read_text())
        summaries = list(run.glob("**/eval_summary.csv"))
        if len(summaries) != 1:
            raise RuntimeError(f"Expected exactly one completed evaluation summary: {run}")
        with summaries[0].open(encoding="utf-8-sig", newline="") as handle:
            trials = list(csv.DictReader(handle))
        rows.append({
            "run":run.name, "attempts":len(trials),
            "target_completed":sum(t.get("termination_reason")=="target_laps_completed" for t in trials),
            "valid_laps":audit["valid_laps"], "full_laps":audit["full_laps"],
            "best_s":audit["best_valid_s"], "median_s":audit["median_valid_s"],
        })
    baseline = next((r for r in rows if r["run"]=="stage0_baseline"),None)
    for row in rows:
        row["median_saved_vs_initial_s"] = (
            baseline["median_s"]-row["median_s"]
            if baseline and baseline["median_s"] is not None and row["median_s"] is not None else None)
    document = {"updated_utc":datetime.now(timezone.utc).isoformat(),
                "note":"Positive saved seconds means faster; observations are not causal proof. In-progress and training aggregates excluded.","runs":rows}
    (STUDY/"stage_results.json").write_text(json.dumps(document,indent=2),encoding="utf-8")
    if rows:
        with (STUDY/"stage_results.csv").open("w",encoding="utf-8-sig",newline="") as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    lines=["# 阶段实测统计", "", "仅列已完成的独立评估；训练汇总和未完成测试不计入。节省秒数为正表示更快，不能单凭该差值断言改善。", "", "|运行|目标完成/尝试|有效/完整圈|最快秒|中位秒|比初始中位节省秒|", "|---|---:|---:|---:|---:|---:|"]
    def show(v):
        return "—" if v is None else f"{v:.6f}"
    for r in rows:
        lines.append(f"|{r['run']}|{r['target_completed']}/{r['attempts']}|{r['valid_laps']}/{r['full_laps']}|{show(r['best_s'])}|{show(r['median_s'])}|{show(r['median_saved_vs_initial_s'])}|")
    (STUDY/"STAGE_RESULTS.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(document,indent=2))


if __name__=="__main__":
    main()
