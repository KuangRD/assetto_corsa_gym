import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pedal_conditioning", Path(__file__).resolve().parents[2]
    / "assetto_corsa_gym/AssettoCorsaEnv/pedal_conditioning.py")
pedals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pedals)


def test_disabled_preserves_input():
    assert pedals.reduce_light_brake_overlap(1., -.2, 0.) == -.2


def test_heavy_braking_and_partial_throttle_unchanged():
    assert pedals.reduce_light_brake_overlap(1., 1., .5) == 1.
    assert pedals.reduce_light_brake_overlap(0., 0., .5) == 0.


def test_light_brake_reduced_without_creating_brake():
    assert pedals.reduce_light_brake_overlap(1., -.2, .5) < -.2
    assert pedals.reduce_light_brake_overlap(1., -1., .5) == -1.


def test_invalid_strength_rejected():
    for strength in [-.1, 1.1, float('nan')]:
        try:
            pedals.reduce_light_brake_overlap(1., 0., strength)
        except ValueError:
            continue
        raise AssertionError('Invalid strength accepted')
