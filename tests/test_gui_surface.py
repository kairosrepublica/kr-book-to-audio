import inspect
import unittest
from kr_book_to_audio import gui


class GuiSurfaceTests(unittest.TestCase):
    def test_gui_uses_compact_tooltips_action_cleanup_and_provider_selectors(self):
        source = inspect.getsource(gui)
        self.assertIn("text='ⓘ'", source)
        self.assertIn('Optional cleanup analysis', source)
        self.assertIn('Apply date/time cleanup', source)
        self.assertIn('Apply repeated-header cleanup', source)
        self.assertIn('Set as default', source)
        self.assertIn('Processing profile', source)
        self.assertIn('TTS engine', source)
        self.assertIn("state='readonly'", source)
        self.assertNotIn('Traditional to Simplified', source)
        self.assertNotIn('self.t2s', source)
        self.assertNotIn('strip_datetime_tags = tk.BooleanVar', source)
        self.assertIn('Recent jobs', source)
        self.assertIn('Resume selected', source)
        self.assertIn('Keep computer awake during long operations', source)
        self.assertIn('Resume synthesis from Part', source)


if __name__ == '__main__':
    unittest.main()
