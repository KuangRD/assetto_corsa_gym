"""Run an explicit sequence of isolated experiments, with a wall-clock deadline.

The manifest contains config, checkpoint and output paths. Training requires
an explicit mode=train entry. Put STOP_QUEUE in the study directory to stop after the
current evaluation. State and command lines are persisted for heartbeat review.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil


ROOT = Path(__file__).resolve().parents[1]


def save(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(str(temporary), str(path))


def active_clients():
    found = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        command = process.info["cmdline"] or []
        if any(Path(part).name in ("train.py", "run_demo_lap.py") for part in command):
            found.append(process.info["pid"])
    return found


def release_controls():
    sys.path.insert(0, str(ROOT / "assetto_corsa_gym"))
    from AssettoCorsaPlugin.plugins.sensors_par.car_control import Controls
    controls = Controls()
    try:
        controls.set_controls(steer=0, acc=-1, brake=1)
    finally:
        controls.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--after-pid", type=int,
                        help="Wait for this existing study coordinator to exit first")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    study = args.manifest.resolve().parent
    deadline = datetime.fromisoformat(manifest["deadline_utc"].replace("Z", "+00:00"))
    jobs = manifest["jobs"]
    for job in jobs:
        if job.get("mode", "eval") not in ("eval", "train"):
            raise ValueError("Unknown job mode")
        for key in ("config", "checkpoint"):
            if not (ROOT / job[key]).is_file():
                raise FileNotFoundError(job[key])
        output = (ROOT / job["output"]).resolve()
        if study not in output.parents:
            raise ValueError("Output must be inside study: " + str(output))
    if args.dry_run:
        print(json.dumps(jobs, indent=2))
        return
    state_path = study / (args.manifest.stem + "_state.json")
    state = {"pid": os.getpid(), "status": "waiting_for_existing_client", "completed": []}
    save(state_path, state)
    if args.after_pid:
        try:
            predecessor = psutil.Process(args.after_pid)
            if not any(Path(part).name == "run_speed_study_queue.py"
                       for part in predecessor.cmdline()):
                raise RuntimeError("Predecessor PID is not a study coordinator")
            state.update(status="waiting_for_coordinator", predecessor_pid=args.after_pid)
            save(state_path, state)
            while predecessor.is_running():
                if datetime.now(timezone.utc) >= deadline or (study / "STOP_QUEUE").exists():
                    state["status"] = "stopped_before_start"
                    save(state_path, state)
                    return
                try:
                    predecessor.wait(timeout=5)
                except psutil.TimeoutExpired:
                    continue
                break
        except psutil.NoSuchProcess:
            pass
    while active_clients():
        if datetime.now(timezone.utc) >= deadline or (study / "STOP_QUEUE").exists():
            state["status"] = "stopped_before_start"
            save(state_path, state)
            return
        time.sleep(5)
    for job in jobs:
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        timeout = int(job.get("timeout_seconds", 1800))
        if remaining < timeout + 60 or (study / "STOP_QUEUE").exists():
            state["status"] = "stopped_between_jobs"
            save(state_path, state)
            return
        output = ROOT / job["output"]
        if output.exists():
            raise FileExistsError("Refusing to overwrite experiment " + str(output))
        if active_clients():
            raise RuntimeError("Another game client started; refusing concurrent control")
        output.mkdir(parents=True)
        mode = job.get("mode", "eval")
        command = [sys.executable, "train.py", "--config", job["config"]]
        if mode == "eval":
            command.append("--test")
        command.extend(["--resume_ckpt", job["checkpoint"]])
        state.update(status="training" if mode == "train" else "evaluating", job=job, command=command,
                     started_utc=datetime.now(timezone.utc).isoformat())
        with (output / "stdout.log").open("w") as stdout, (output / "stderr.log").open("w") as stderr:
            child = subprocess.Popen(command, cwd=str(ROOT), stdout=stdout, stderr=stderr)
            state["child_pid"] = child.pid
            save(state_path, state)
            try:
                code = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if mode == "train":
                    subprocess.run([sys.executable, "scripts/request_training_checkpoint.py",
                                    "--run-dir", str(output), "--stop-after-save", "--no-wait"],
                                   cwd=str(ROOT), timeout=30)
                    try:
                        child.wait(timeout=120)
                    except subprocess.TimeoutExpired:
                        child.terminate()
                        child.wait(timeout=30)
                        release_controls()
                else:
                    child.terminate()
                    child.wait(timeout=30)
                    release_controls()
                state.update(status="job_timeout", child_pid=None)
                save(state_path, state)
                return
        record = dict(job, exit_code=code)
        if code == 0:
            audit = subprocess.run([sys.executable, "scripts/analyze_speed_study.py", str(output)],
                                   cwd=str(ROOT), capture_output=True, text=True)
            record["audit_exit_code"] = audit.returncode
            record["audit_summary"] = audit.stdout.strip()
            if audit.returncode:
                record["audit_error"] = audit.stderr
        state["completed"].append(record)
        state["child_pid"] = None
        state["status"] = "between_jobs" if code == 0 else "evaluation_error"
        save(state_path, state)
        if code != 0:
            return
        time.sleep(2)
    state["status"] = "queue_complete"
    save(state_path, state)


if __name__ == "__main__":
    main()
