import unittest
from kr_book_to_audio.gui import (
    DEFAULT_WINDOW_WIDTH,
    MIN_WINDOW_WIDTH,
    compute_window_geometry,
)

class ResponsiveGuiTests(unittest.TestCase):
    def test_owner_2160p_screen_defaults_to_exactly_1200_by_1900(self):
        geometry, mode = compute_window_geometry(3840, 2160)
        self.assertEqual(geometry, '1200x1900')
        self.assertEqual(mode, 'expanded')

    def test_screen_height_above_1900_uses_exactly_1900_height(self):
        geometry, _ = compute_window_geometry(2560, 1901)
        self.assertEqual(geometry.split('x')[1], '1900')

    def test_screen_height_equal_to_1900_applies_safe_margin(self):
        geometry, _ = compute_window_geometry(2560, 1900)
        self.assertEqual(geometry.split('x')[1], '1780')

    def test_default_and_minimum_width_contract(self):
        geometry, _ = compute_window_geometry(3840, 2160)
        self.assertEqual(int(geometry.split('x')[0]), DEFAULT_WINDOW_WIDTH)
        geometry, _ = compute_window_geometry(1100, 900)
        self.assertEqual(int(geometry.split('x')[0]), MIN_WINDOW_WIDTH)

    def test_small_screen_height_is_clamped_and_compact(self):
        geometry, mode = compute_window_geometry(1366, 768)
        width, height = (int(value) for value in geometry.split('x'))
        self.assertEqual(width, 1200)
        self.assertLessEqual(height, 648)
        self.assertEqual(mode, 'compact')

    def test_saved_large_geometry_is_clamped_to_current_screen(self):
        geometry, _ = compute_window_geometry(1366, 768, '3000x2000+0+0')
        width, height = (int(value) for value in geometry.split('x'))
        self.assertLessEqual(width, 1286)
        self.assertGreaterEqual(width, MIN_WINDOW_WIDTH)
        self.assertLessEqual(height, 648)

if __name__ == '__main__':
    unittest.main()
