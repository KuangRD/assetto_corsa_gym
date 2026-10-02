"""Build a RaceRoom custom control set that explicitly includes vJoy."""

import argparse
import re
from pathlib import Path


VJOY_DEVICE_ID = 3199013428

CONTROL_REPLACEMENTS = {
    "Device Count": 'Device Count="1"',
    "Control - Steer Left": 'Control - Steer Left="(1, 2, 0, 0)"',
    "Control - Steer Right": 'Control - Steer Right="(1, 1, 0, 0)"',
    "Control - Accelerate": 'Control - Accelerate="(1, 3, 0, 0)"',
    "Control - Brake": 'Control - Brake="(1, 5, 0, 0)"',
    "Control - Shift Up": 'Control - Shift Up="(1, 1, 0, 8)"',
    "Control - Shift Down": 'Control - Shift Down="(1, 2, 0, 8)"',
}


def device_block():
    lines = [
        'DeviceName[00]="vJoy Device"',
        'DeviceId[00]="({}, -1, -1, 0)"'.format(VJOY_DEVICE_ID),
    ]
    for axis in range(8):
        center = "0.5" if axis == 0 or axis >= 3 else "0.0"
        prefix = "Axis [00, {:02d}]".format(axis)
        lines.extend(
            [
                '{} Dead Zone="0.0"'.format(prefix),
                '{} Sensitivity="0.5"'.format(prefix),
                '{} Center="{}"'.format(prefix, center),
                '{} Range="1.0"'.format(prefix),
                'FFB Joy[00] Axis[{:02d}] Spring Saturation Pos="1.0"'.format(axis),
                'FFB Joy[00] Axis[{:02d}] Spring Coefficient Pos="1.0"'.format(axis),
                'FFB Joy[00] Axis[{:02d}] Spring Saturation Neg="1.0"'.format(axis),
                'FFB Joy[00] Axis[{:02d}] Spring Coefficient Neg="1.0"'.format(axis),
            ]
        )
    return lines


def build_profile(source, output, profile_name):
    source_text = source.read_text(encoding="utf-8")
    if "DeviceName[00]" in source_text:
        raise ValueError("source profile already contains a device section")

    lines = source_text.splitlines()
    replaced = set()
    result = []
    for line in lines:
        if line.startswith('Name="'):
            result.append('Name="{}"'.format(profile_name))
            continue
        match = re.match(r"^([^=]+)=", line)
        key = match.group(1) if match else None
        if key in CONTROL_REPLACEMENTS:
            result.append(CONTROL_REPLACEMENTS[key])
            replaced.add(key)
        else:
            result.append(line)

    missing = sorted(set(CONTROL_REPLACEMENTS) - replaced)
    if missing:
        raise ValueError("source profile is missing keys: {}".format(missing))
    if not any(line.startswith('File Version="') for line in result):
        raise ValueError("source profile has no File Version marker")

    result.extend(device_block())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(result) + "\n", encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--name", default="vJoy_RL_Research_Explicit", help="RaceRoom profile name"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    build_profile(args.source, args.output, args.name)
    print("Built {}".format(args.output))


if __name__ == "__main__":
    main()
