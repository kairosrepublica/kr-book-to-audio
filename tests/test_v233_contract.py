from pathlib import Path
import inspect
import unittest
from kr_book_to_audio import gui

ROOT = Path(__file__).resolve().parents[1]

class V233ContractTests(unittest.TestCase):
    def test_release_notes_exist(self):
        self.assertTrue((ROOT / 'docs' / 'RELEASE_NOTES_ISTANBUL_RELEASE_v2.3.3.md').is_file())

    def test_windows_physical_visible_height_adapter_is_used(self):
        source = inspect.getsource(gui.App._outer_scroll_enabled)
        self.assertIn('visible_window_height_px(self.root)', source)
        adapter = inspect.getsource(gui.visible_window_height_px)
        self.assertIn('DwmGetWindowAttribute', adapter)
        self.assertIn('DWMWA_EXTENDED_FRAME_BOUNDS', adapter)

    def test_fixed_mode_consumes_outer_wheel_event(self):
        source = inspect.getsource(gui.App._scroll_outer_viewport)
        self.assertIn("if not self._outer_scroll_enabled():", source)
        self.assertIn("return 'break'", source)

    def test_real_windows_outer_scroll_probe_is_shipped(self):
        path = ROOT / 'packaging' / 'verify_outer_scroll_windows.py'
        self.assertTrue(path.is_file())
        text = path.read_text(encoding='utf-8')
        self.assertIn('TARGET_RUNTIME_FIXTURE PASS: real Windows outer-scroll interaction probe', text)
        self.assertIn('high_window', text)
        self.assertIn('low_window', text)

    def test_historical_v232_release_notes_remain_historically_accurate(self):
        text = (ROOT / 'docs' / 'RELEASE_NOTES_ISTANBUL_RELEASE_v2.3.2.md').read_text(encoding='utf-8')
        self.assertIn('Istanbul Release v2.3.2', text)

if __name__ == '__main__':
    unittest.main()
