import inspect
import unittest
from kr_book_to_audio import gui

class RuntimeVisibilityTests(unittest.TestCase):
    def test_gui_has_timestamped_log_green_running_row_and_auto_centering(self):
        source=inspect.getsource(gui)
        self.assertIn("strftime('%H:%M:%S')", source)
        self.assertIn("self.log.see('end')", source)
        self.assertIn("tag_configure('running'", source)
        self.assertIn("_center_part_status", source)
        self.assertIn("% estimated", source)
        self.assertIn("_log_progress_bucket", source)
        self.assertIn("min(94", source)
        self.assertIn("100% done", source)

if __name__=='__main__': unittest.main()
