import unittest
from kr_book_to_audio.gui import compute_window_geometry

class ResponsiveGuiTests(unittest.TestCase):
    def test_owner_2160p_screen_defaults_to_1900_height(self):
        geometry, mode=compute_window_geometry(3840,2160)
        self.assertEqual(geometry.split('x')[1],'1900')
        self.assertEqual(mode,'expanded')

    def test_small_screen_is_clamped_and_compact(self):
        geometry, mode=compute_window_geometry(1366,768)
        width,height=(int(value) for value in geometry.split('x'))
        self.assertLessEqual(width,1286)
        self.assertLessEqual(height,648)
        self.assertEqual(mode,'compact')

    def test_saved_large_geometry_is_clamped_to_current_screen(self):
        geometry,_=compute_window_geometry(1366,768,'3000x2000+0+0')
        width,height=(int(value) for value in geometry.split('x'))
        self.assertLessEqual(width,1286); self.assertLessEqual(height,648)
