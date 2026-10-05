import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "reference_reward", Path(__file__).resolve().parents[2] /
    "assetto_corsa_gym/AssettoCorsaEnv/reference_reward.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
reward = module.reference_line_multiplier


class ReferenceRewardTests(unittest.TestCase):
    def test_default_matches_old_reward(self):
        for gap in [-15, -2, 0, 1, 12, 18]:
            self.assertEqual(reward(gap), 1.0 - abs(gap) / 12.0)

    def test_scale_halves_penalty(self):
        self.assertAlmostEqual(1-reward(3, 24), (1-reward(3))/2)

    def test_corridor_symmetric_continuous_and_not_clamped(self):
        self.assertEqual(reward(-1, 12, 1), 1)
        self.assertEqual(reward(1, 12, 1), 1)
        self.assertAlmostEqual(reward(1.00001,12,1),1-0.00001/12)
        self.assertEqual(reward(-25,12,1),-1)

    def test_bad_parameters_rejected(self):
        for scale, corridor in [(0,0),(-1,0),(float('inf'),0),(12,-1),(12,float('nan'))]:
            with self.assertRaises(ValueError):
                reward(1,scale,corridor)
