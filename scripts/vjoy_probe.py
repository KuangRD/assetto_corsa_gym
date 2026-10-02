"""Diagnose vJoy and optionally send a short, explicitly armed test pulse."""

import argparse
import sys
import time
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from assetto_corsa_gym.RacingEnv.controls.vjoy import (  # noqa: E402
    HID_USAGE,
    VJoyStatus,
    WindowsVJoyDevice,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, default=1)
    parser.add_argument("--axis", choices=("x", "y", "z"))
    parser.add_argument(
        "--positions",
        type=float,
        nargs="+",
        help="axis positions in percent; requires --axis",
    )
    parser.add_argument("--button", type=int)
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0.75,
        help="seconds to hold each test position (default: 0.75)",
    )
    parser.add_argument(
        "--start-delay",
        type=float,
        default=0.0,
        help="seconds to wait before acquiring and sending output",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="number of times to repeat the axis position sequence",
    )
    parser.add_argument(
        "--armed",
        action="store_true",
        help="required before any axis or button output is sent",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0.1 <= args.hold_seconds <= 10.0:
        raise ValueError("--hold-seconds must be between 0.1 and 10")
    if not 0.0 <= args.start_delay <= 60.0:
        raise ValueError("--start-delay must be between 0 and 60")
    if not 1 <= args.repeat <= 100:
        raise ValueError("--repeat must be between 1 and 100")
    if args.positions and not args.axis:
        raise ValueError("--positions requires --axis")
    if args.positions and any(value < 0.0 or value > 100.0 for value in args.positions):
        raise ValueError("all --positions values must be between 0 and 100")
    device = WindowsVJoyDevice(args.device)
    device.assert_enabled()
    print("vJoy driver version: 0x{:04X}".format(device.version))
    print("Device {} status: {}".format(args.device, device.status.name))
    for axis in ("x", "y", "z"):
        try:
            print("Axis {} bounds: {}".format(axis.upper(), device.axis_bounds(axis)))
        except Exception as error:
            print("Axis {} unavailable: {}".format(axis.upper(), error))

    if args.axis is None and args.button is None:
        if device.status == VJoyStatus.BUSY:
            print("Device is currently held by vJoyFeeder or another writer.")
        return 0
    if not args.armed:
        print("Refusing to send output without --armed", file=sys.stderr)
        return 2

    with device:
        positions = args.positions or (50.0, 80.0, 20.0, 50.0)
        if args.axis:
            # Hold the initial (normally neutral) position while the game
            # enumerates the acquired virtual device.
            device.set_axis_percent(args.axis, positions[0])
        if args.start_delay:
            print(
                "Holding Device {} for {:.1f}s before output...".format(
                    args.device, args.start_delay
                )
            )
            time.sleep(args.start_delay)

        if args.axis:
            print(
                "Pulsing {} axis: {}".format(
                    args.axis.upper(),
                    " -> ".join("{}%".format(value) for value in positions),
                )
            )
            for _ in range(args.repeat):
                for percent in positions:
                    device.set_axis_percent(args.axis, percent)
                    time.sleep(args.hold_seconds)
        if args.button:
            print(
                "Pulsing button {} ({} times)".format(
                    args.button, args.repeat
                )
            )
            for _ in range(args.repeat):
                device.set_button(args.button, True)
                time.sleep(args.hold_seconds)
                device.set_button(args.button, False)
                time.sleep(args.hold_seconds)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("vJoy probe failed: {}".format(error), file=sys.stderr)
        raise SystemExit(1)
