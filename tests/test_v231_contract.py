from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class V231ContractTests(unittest.TestCase):
    def test_readme_removes_outdated_top_hero_screenshot_reference(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertNotIn('![KR Book To Audio desktop GUI](docs/images/kr_book_to_audio_gui_istanbul_release_2_0.png)', text)

    def test_readme_normalizes_historical_headings(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertNotIn('Historical interface evidence', text)
        self.assertIn('## Historical interface', text)

    def test_release_notes_exist(self):
        self.assertTrue((ROOT / 'docs' / 'RELEASE_NOTES_ISTANBUL_RELEASE_v2.3.1.md').is_file())

if __name__ == '__main__':
    unittest.main()
