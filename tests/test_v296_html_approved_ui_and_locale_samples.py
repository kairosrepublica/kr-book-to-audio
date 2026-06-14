from __future__ import annotations
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class HtmlApprovedUiAndLocaleSampleTests(unittest.TestCase):
    def test_html_approved_shell_sections_exist(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        for token in ('Source and storage', 'Current workspace', 'Text and speech settings', 'Text process', 'Audio process', 'Run log', 'Status', 'Refresh voice samples', 'Play sample'):
            self.assertIn(token, source)
        self.assertNotIn('Local-first audiobook production workspace', source)
        self.assertNotIn('ANALYSIS REQUIRED AFTER RELOAD', source)

    def test_locale_specific_preview_samples_exist(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'edge_voice_samples.py').read_text(encoding='utf-8')
        for token in ("'zh':", "'tr':", "'ja':", "'es':", "'fr':", "'de':"):
            self.assertIn(token, source)
        self.assertIn('English fallback is prohibited', source)

if __name__ == '__main__':
    unittest.main()
