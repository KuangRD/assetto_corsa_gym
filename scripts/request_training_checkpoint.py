"""Request a complete checkpoint from a running Assetto Corsa trainer.

The trainer polls a control file between environment transitions, ends the
current episode on a replay-safe boundary, saves a complete checkpoint, and
then writes a request-specific status file. No process signal or shared-memory
mutation is required.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(str(temporary_path), str(path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ask a running trainer to save a complete checkpoint.")
    parser.add_argument(
        "--run-dir",
        required=True,
        type=Path,
        help="Training output directory containing model/, summary/, and control/.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Seconds to wait for completion (default: 300).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.5,
        help="Seconds between status checks (default: 0.5).",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Submit the request and return immediately.",
    )
    parser.add_argument(
        "--stop-after-save",
        action="store_true",
        help="Ask the trainer to exit cleanly immediately after the save succeeds.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    if not run_dir.is_dir():
        print(f"Run directory does not exist: {run_dir}", file=sys.stderr)
        return 2
    if args.timeout <= 0 or args.poll_interval <= 0:
        print("--timeout and --poll-interval must be positive", file=sys.stderr)
        return 2

    control_dir = run_dir / "control"
    request_path = control_dir / "save_checkpoint.request.json"
    processing_path = control_dir / "save_checkpoint.processing.json"
    if request_path.exists() or processing_path.exists():
        print(
            "Another checkpoint request is pending or a previous request was "
            f"interrupted. Inspect: {control_dir}",
            file=sys.stderr,
        )
        return 3

    request_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    status_path = control_dir / f"checkpoint.status.{request_id}.json"
    payload = {
        "request_id": request_id,
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "requested_by": f"{socket.gethostname()}:{os.getpid()}",
        "stop_after_save": bool(args.stop_after_save),
    }
    write_json_atomic(request_path, payload)
    print(f"Checkpoint request submitted: {request_id}")
    print(f"Request file: {request_path}")

    if args.no_wait:
        return 0

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(args.poll_interval)
                continue
            if status.get("status") == "success":
                print(f"Checkpoint saved at total step {status['total_step']}")
                print(f"Checkpoint: {status['checkpoint_path']}")
                if status.get("stop_after_save"):
                    print("Trainer was asked to exit cleanly after saving.")
                return 0
            print(
                "Checkpoint request failed: " + str(status.get("error", status)),
                file=sys.stderr,
            )
            return 1
        time.sleep(args.poll_interval)

    print(
        f"Timed out after {args.timeout:.1f}s. The request may still complete; "
        f"inspect {control_dir} before submitting another one.",
        file=sys.stderr,
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
