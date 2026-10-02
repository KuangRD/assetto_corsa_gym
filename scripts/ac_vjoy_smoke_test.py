"""Explicitly armed, stationary Assetto Corsa vJoy control smoke test."""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from omegaconf import OmegaConf


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "assetto_corsa_gym"))

import AssettoCorsaEnv.assettoCorsa as assetto_corsa  # noqa: E402


STATE_FIELDS = (
    "speed",
    "actualGear",
    "steerAngle",
    "accStatus",
    "brakeStatus",
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPOSITORY_ROOT / "config.yml")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "outputs" / "ac_vjoy_smoke_test.json",
    )
    parser.add_argument("--armed", action="store_true")
    parser.add_argument("--maximum-speed-ms", type=float, default=0.5)
    return parser.parse_args()


def compact_state(state):
    return {field: state.get(field) for field in STATE_FIELDS}


def run_command(client, label, steer, acc, brake, duration=0.6):
    client.controls.set_controls(steer=steer, acc=acc, brake=brake)
    samples = []
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        client.respond_to_server()
        samples.append(compact_state(client.step_sim()))
    return {"label": label, "samples": samples}


def pulse_shift(client, label, shift_up):
    client.controls.set_controls(
        steer=0,
        acc=-1,
        brake=1,
        enable_gear_shift=True,
        shift_up=shift_up,
        shift_down=not shift_up,
    )
    client.respond_to_server()
    pressed = compact_state(client.step_sim())
    time.sleep(0.08)
    client.controls.set_controls(
        steer=0,
        acc=-1,
        brake=1,
        enable_gear_shift=True,
        shift_up=False,
        shift_down=False,
    )
    client.respond_to_server()
    released = compact_state(client.step_sim())
    settled = run_command(client, label + "_settled", 0, -1, 1, 0.5)
    return {"label": label, "pressed": pressed, "released": released, "settled": settled}


def extrema(samples, field):
    values = [sample[field] for sample in samples if sample.get(field) is not None]
    if not values:
        return None
    return {"min": min(values), "max": max(values), "last": values[-1]}


def main():
    args = parse_args()
    if not args.armed:
        print("Refusing to control Assetto Corsa without --armed", file=sys.stderr)
        return 2

    config = OmegaConf.load(str(args.config))
    config.AssettoCorsa.screen_capture_enable = False
    client = assetto_corsa.make_client_only(config.AssettoCorsa)
    result = {
        "started_at": datetime.now().astimezone().isoformat(),
        "commands": [],
        "passed": False,
    }

    try:
        client.setup_connection()
        initial = compact_state(client.state)
        result["initial"] = initial
        speed = float(initial.get("speed") or 0.0)
        if abs(speed) > args.maximum_speed_ms:
            raise RuntimeError(
                "Refusing test: initial speed {:.3f} m/s exceeds {:.3f} m/s".format(
                    speed, args.maximum_speed_ms
                )
            )

        result["commands"].append(run_command(client, "safe_brake", 0, -1, 1))
        result["commands"].append(run_command(client, "steer_left", -0.2, -1, 1))
        result["commands"].append(run_command(client, "steer_center_1", 0, -1, 1, 0.3))
        result["commands"].append(run_command(client, "steer_right", 0.2, -1, 1))
        result["commands"].append(run_command(client, "steer_center_2", 0, -1, 1, 0.3))
        result["commands"].append(run_command(client, "light_throttle", 0, -0.5, 1))
        result["commands"].append(run_command(client, "safe_brake_2", 0, -1, 1))

        latest_speed = float(result["commands"][-1]["samples"][-1]["speed"] or 0.0)
        if abs(latest_speed) <= args.maximum_speed_ms:
            result["shift_up"] = pulse_shift(client, "shift_up", True)
            result["shift_down"] = pulse_shift(client, "shift_down", False)
        else:
            result["shift_skipped"] = "speed {:.3f} m/s".format(latest_speed)

        result["final_safe_brake"] = run_command(client, "final_safe_brake", 0, -1, 1)

        by_label = {item["label"]: item for item in result["commands"]}
        summary = {
            "steer_left": extrema(by_label["steer_left"]["samples"], "steerAngle"),
            "steer_right": extrema(by_label["steer_right"]["samples"], "steerAngle"),
            "throttle": extrema(by_label["light_throttle"]["samples"], "accStatus"),
            "brake": extrema(by_label["safe_brake_2"]["samples"], "brakeStatus"),
            "speed": extrema(
                [sample for item in result["commands"] for sample in item["samples"]],
                "speed",
            ),
        }
        result["summary"] = summary

        left = summary["steer_left"]
        right = summary["steer_right"]
        throttle = summary["throttle"]
        brake = summary["brake"]
        result["checks"] = {
            "steering_changed": bool(
                left and right and abs(left["last"] - right["last"]) > 0.02
            ),
            "throttle_registered": bool(throttle and throttle["max"] > 0.1),
            "brake_registered": bool(brake and brake["max"] > 0.5),
            "stayed_low_speed": bool(summary["speed"] and summary["speed"]["max"] <= 1.0),
        }
        result["passed"] = all(result["checks"].values())
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        try:
            # Leave the virtual device at center/no throttle/full brake.
            client.controls.set_controls(steer=0, acc=-1, brake=1)
            client.controls.apply_local_controls()
        except Exception:
            pass
        try:
            client.reply_to_server("disconnect")
            if client.socket:
                client.socket.close()
                client.socket = None
        except Exception:
            pass
        try:
            client.controls.local_controls.close()
        except Exception:
            pass
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.output), **result.get("summary", {}), "checks": result.get("checks"), "passed": result["passed"]}, indent=2))

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
