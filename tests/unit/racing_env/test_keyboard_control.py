import ctypes
import unittest

from assetto_corsa_gym.RacingEnv.controls.keyboard import (
    INPUT,
    KEYBDINPUT,
    MOUSEINPUT,
    SCAN_CODES,
)


class KeyboardLayoutTests(unittest.TestCase):
    def test_send_input_layout_matches_64_bit_windows(self):
        self.assertEqual(ctypes.sizeof(KEYBDINPUT), 24)
        self.assertEqual(ctypes.sizeof(MOUSEINPUT), 32)
        self.assertEqual(ctypes.sizeof(INPUT), 40)

    def test_configured_bindings_use_physical_scan_codes(self):
        self.assertEqual(SCAN_CODES["q"], (0x10, False))
        self.assertEqual(SCAN_CODES["z"], (0x2C, False))
        self.assertEqual(SCAN_CODES["up"], (0x48, True))
        self.assertEqual(SCAN_CODES["down"], (0x50, True))


if __name__ == "__main__":
    unittest.main()
