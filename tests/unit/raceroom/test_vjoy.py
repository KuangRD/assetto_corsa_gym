import unittest

from assetto_corsa_gym.RacingEnv.controls.vjoy import scale_percent


class VJoyScalingTests(unittest.TestCase):
    def test_percent_endpoints_and_center(self):
        self.assertEqual(scale_percent(0, 0, 32768), 0)
        self.assertEqual(scale_percent(50, 0, 32768), 16384)
        self.assertEqual(scale_percent(100, 0, 32768), 32768)

    def test_percent_rejects_out_of_range_values(self):
        with self.assertRaises(ValueError):
            scale_percent(-0.1, 0, 32768)
        with self.assertRaises(ValueError):
            scale_percent(100.1, 0, 32768)


if __name__ == "__main__":
    unittest.main()
