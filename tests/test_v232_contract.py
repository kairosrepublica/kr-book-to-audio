from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class V232ContractTests(unittest.TestCase):
    def test_release_notes_exist(self):
        self.assertTrue((ROOT / 'docs' / 'RELEASE_NOTES_ISTANBUL_RELEASE_v2.3.2.md').is_file())

    def test_historical_v231_release_notes_remain_historically_accurate(self):
        text = (ROOT / 'docs' / 'RELEASE_NOTES_ISTANBUL_RELEASE_v2.3.1.md').read_text(encoding='utf-8')
        self.assertIn('screen height > 1900 px: default height = 1900 px', text)

    def test_current_readme_uses_1870_policy(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('## Istanbul Release v2.3.2', text)
        self.assertIn('exactly 1870 px high', text)
        self.assertIn('actual window height is at least 1870 px', text)

if __name__ == '__main__':
    unittest.main()
