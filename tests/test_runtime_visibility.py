from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class RuntimeVisibilityTests(unittest.TestCase):
    def test_gui_has_timestamped_log_green_running_row_and_auto_centering(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn('self.log_progress = ttk.Progressbar', source)
        self.assertIn("roles[key] = 'running'", source)
        self.assertIn('self.status_current_progress = ttk.Progressbar', source)
        self.assertIn('self.overall_progress = self.log_progress', source)
        self.assertIn('self.current_progress = self.status_current_progress', source)
        self.assertNotIn('self.current_progress = ttk.Progressbar', source)

if __name__ == '__main__': unittest.main()
