import unittest
from pathlib import Path

import numpy as np

from assetto_corsa_gym.AssettoCorsaEnv.curvature import curvature_splines
from assetto_corsa_gym.AssettoCorsaEnv.reference_lap import ReferenceLap


class CurvatureSeamTests(unittest.TestCase):
    def test_periodic_curvature_is_continuous_on_a_circle(self):
        angles = np.linspace(0.0, 2.0 * np.pi, 360, endpoint=False)
        radius = 50.0
        curvature = curvature_splines(
            radius * np.cos(angles),
            radius * np.sin(angles),
            periodic=True,
        )

        self.assertEqual(curvature.shape, angles.shape)
        self.assertAlmostEqual(curvature.mean(), 1.0 / radius, delta=2e-4)
        self.assertLess(np.max(np.abs(curvature - 1.0 / radius)), 0.003)
        self.assertAlmostEqual(curvature[0], curvature[-1], delta=3e-4)

    def test_silverstone_lookahead_is_fixed_size_and_continuous_at_seam(self):
        repo_root = Path(__file__).resolve().parents[3]
        reference_file = (
            repo_root
            / "assetto_corsa_gym"
            / "AssettoCorsaConfigs"
            / "tracks"
            / "ks_silverstone-gp-racing_line.csv"
        )
        reference_lap = ReferenceLap(reference_file, use_target_speed=False)

        before = reference_lap.get_curvature_segment(5803.75, 300.0, 12)
        after = reference_lap.get_curvature_segment(5804.25, 300.0, 12)

        self.assertEqual(before.shape, (12,))
        self.assertEqual(after.shape, (12,))
        self.assertLess(np.linalg.norm(after - before), 0.005)

    def test_lookahead_uses_fixed_distance_offsets(self):
        reference_lap = ReferenceLap.__new__(ReferenceLap)
        distances = np.arange(10.0)
        channel = distances.copy()

        vector, _, patch = reference_lap.getLADVector(
            distances, dist=8.0, LA_dist=8.0, vector_size=4, channel=channel
        )

        np.testing.assert_allclose(vector, [8.0, 0.0, 2.0, 4.0])
        self.assertEqual(patch, 6.0)


if __name__ == "__main__":
    unittest.main()
