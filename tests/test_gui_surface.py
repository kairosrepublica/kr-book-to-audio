import inspect
import unittest
from kr_book_to_audio import gui


class GuiSurfaceTests(unittest.TestCase):
    def test_gui_uses_compact_tooltip_surface_and_no_script_conversion_control(self):
        source = inspect.getsource(gui)
        self.assertIn("text='ⓘ'", source)
        self.assertIn('Optional cleanup', source)
        self.assertIn('Remove metadata-like date/time tags', source)
        self.assertIn('Remove repeated headers and junk', source)
        self.assertIn('Set as default', source)
        self.assertNotIn('Traditional to Simplified', source)
        self.assertNotIn('self.t2s', source)


if __name__ == '__main__':
    unittest.main()
