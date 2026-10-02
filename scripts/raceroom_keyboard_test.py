"""Explicitly armed, low-speed keyboard control and gear feedback test."""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Tuple


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from assetto_corsa_gym.RaceRoom.session_guard import (
    RaceRoomSessionGuard,
    SessionGuardPolicy,
)
from assetto_corsa_gym.RaceRoom.shared_memory import (
    RaceRoomSharedMemory,
    SharedMemorySnapshot,
)
from assetto_corsa_gym.RacingEnv.controls.keyboard import WindowsKeyboardBackend
from assetto_corsa_gym.RacingEnv.errors import SimulatorError, TelemetryTimeoutError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--armed", action="store_true")
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--countdown", type=float, default=10.0)
    parser.add_argument("--max-speed", type=float, default=5.0)
    parser.add_argument("--axis-motion", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def wait_for(
    reader: RaceRoomSharedMemory,
    guard: RaceRoomSessionGuard,
    snapshot: SharedMemorySnapshot,
    predicate: Callable[[SharedMemorySnapshot], bool],
    timeout_s: float,
) -> SharedMemorySnapshot:
    deadline = time.perf_counter() + timeout_s
    current = snapshot
    while time.perf_counter() < deadline:
        current = reader.wait_for_snapshot(current.sequence, min(0.1, timeout_s))
        guard.assert_control_allowed(current.data)
        if predicate(current):
            return current
    raise TelemetryTimeoutError("Expected control feedback did not arrive")


def tap_and_confirm_gear(
    backend: WindowsKeyboardBackend,
    reader: RaceRoomSharedMemory,
    guard: RaceRoomSessionGuard,
    snapshot: SharedMemorySnapshot,
    key: str,
    expected: Callable[[int], bool],
) -> Tuple[SharedMemorySnapshot, int]:
    backend.assert_game_has_focus()
    guard.assert_control_allowed(snapshot.data)
    backend.key_down(key)
    time.sleep(0.08)
    backend.key_up(key)
    snapshot = wait_for(
        reader,
        guard,
        snapshot,
        lambda item: expected(int(item.data.gear)),
        1.5,
    )
    return snapshot, int(snapshot.data.gear)


def hold_with_guard(
    backend: WindowsKeyboardBackend,
    reader: RaceRoomSharedMemory,
    guard: RaceRoomSessionGuard,
    snapshot: SharedMemorySnapshot,
    key: str,
    duration_s: float,
    max_speed_mps: float,
) -> Tuple[SharedMemorySnapshot, float]:
    deadline = time.perf_counter() + duration_s
    maximum_speed = float(snapshot.data.car_speed)
    backend.assert_game_has_focus()
    guard.assert_control_allowed(snapshot.data)
    backend.key_down(key)
    try:
        while time.perf_counter() < deadline:
            snapshot = reader.wait_for_snapshot(snapshot.sequence, 0.1)
            backend.assert_game_has_focus()
            guard.assert_control_allowed(snapshot.data)
            maximum_speed = max(maximum_speed, float(snapshot.data.car_speed))
            if maximum_speed > max_speed_mps:
                raise SimulatorError(
                    "Low-speed test exceeded {:.2f} m/s".format(max_speed_mps)
                )
    finally:
        backend.key_up(key)
    return snapshot, maximum_speed


def run_test(args: argparse.Namespace) -> Dict[str, Any]:
    if not args.armed:
        raise SimulatorError("Live keyboard test requires explicit --armed")

    reader = RaceRoomSharedMemory()
    backend = WindowsKeyboardBackend(args.process_id)
    guard = RaceRoomSessionGuard(
        SessionGuardPolicy(
            expected_track_id=2021,
            expected_layout_id=2027,
            expected_car_id=11325,
        )
    )
    results: Dict[str, Any] = {"armed": True, "process_id": args.process_id}
    try:
        snapshot = reader.open()
        guard.assert_control_allowed(snapshot.data)
        results["initial_gear"] = int(snapshot.data.gear)
        results["initial_speed_mps"] = float(snapshot.data.car_speed)

        time.sleep(args.countdown)
        backend.assert_game_has_focus()
        snapshot = reader.read_consistent_snapshot()
        guard.assert_control_allowed(snapshot.data)

        snapshot, _ = hold_with_guard(
            backend, reader, guard, snapshot, "left", 0.35, args.max_speed
        )
        results["left_feedback"] = float(snapshot.data.steer_input_raw)
        snapshot, _ = hold_with_guard(
            backend, reader, guard, snapshot, "right", 0.35, args.max_speed
        )
        results["right_feedback"] = float(snapshot.data.steer_input_raw)

        snapshot, maximum_speed = hold_with_guard(
            backend, reader, guard, snapshot, "up", 0.5, args.max_speed
        )
        results["throttle_feedback"] = float(snapshot.data.throttle_raw)
        results["maximum_speed_mps"] = maximum_speed

        original_gear = int(snapshot.data.gear)
        snapshot, upshift_gear = tap_and_confirm_gear(
            backend,
            reader,
            guard,
            snapshot,
            "q",
            lambda gear: gear > original_gear,
        )
        results["upshift_gear"] = upshift_gear
        snapshot, downshift_gear = tap_and_confirm_gear(
            backend,
            reader,
            guard,
            snapshot,
            "z",
            lambda gear: gear == original_gear,
        )
        results["downshift_gear"] = downshift_gear

        snapshot, _ = hold_with_guard(
            backend, reader, guard, snapshot, "down", 0.7, args.max_speed
        )
        results["brake_feedback"] = float(snapshot.data.brake_raw)
        results["final_speed_mps"] = float(snapshot.data.car_speed)
        results["final_gear"] = int(snapshot.data.gear)

        if args.axis_motion:
            motion_results = {}
            for label, steering_key in (
                ("straight", None),
                ("left", "left"),
                ("right", "right"),
            ):
                if steering_key is not None:
                    backend.key_down(steering_key)
                try:
                    snapshot, phase_max_speed = hold_with_guard(
                        backend,
                        reader,
                        guard,
                        snapshot,
                        "up",
                        0.8,
                        args.max_speed,
                    )
                finally:
                    if steering_key is not None:
                        backend.key_up(steering_key)
                phase_result = {
                    "max_speed_mps": phase_max_speed,
                    "gear": int(snapshot.data.gear),
                    "steer_feedback": float(snapshot.data.steer_input_raw),
                }
                snapshot, _ = hold_with_guard(
                    backend,
                    reader,
                    guard,
                    snapshot,
                    "down",
                    0.8,
                    args.max_speed,
                )
                phase_result["stopped_speed_mps"] = float(
                    snapshot.data.car_speed
                )
                motion_results[label] = phase_result
            results["axis_motion"] = motion_results

        results["passed"] = True
        return results
    finally:
        backend.release_all()
        try:
            if reader.connected:
                safe_snapshot = reader.read_consistent_snapshot()
                guard.assert_control_allowed(safe_snapshot.data)
                backend.assert_game_has_focus()
                backend.key_down("down")
                time.sleep(0.8)
                backend.key_up("down")
        except Exception:
            pass
        finally:
            backend.release_all()
            reader.close()


def main() -> int:
    args = parse_args()
    try:
        result = run_test(args)
    except SimulatorError as error:
        result = {"armed": args.armed, "passed": False, "error": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
