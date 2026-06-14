from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import inspect
import unittest
from kr_book_to_audio import gui


class GuiSurfaceTests(unittest.TestCase):
    def test_gui_uses_process_order_hidden_export_and_advanced_recovery(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        for token in ('Source and storage', 'Current workspace', 'Text and speech settings', 'OCR', 'Text process', 'Audio process', 'Run log', 'Status', 'Advanced recovery', 'Export diagnostic ZIP'):
            self.assertIn(token, source)
        self.assertNotIn('Local-first audiobook production workspace', source)
        self.assertNotIn('ANALYSIS REQUIRED AFTER RELOAD', source)


if __name__ == '__main__':
    unittest.main()
