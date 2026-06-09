import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class V230ContractTests(unittest.TestCase):
    def test_public_historical_v210_screenshot_is_documented(self):
        screenshot=ROOT/'docs/images/kr_book_to_audio_gui_istanbul_release_v2_1_0.png'
        self.assertTrue(screenshot.exists())
        self.assertIn('kr_book_to_audio_gui_istanbul_release_v2_1_0.png',(ROOT/'README.md').read_text(encoding='utf-8'))

    def test_product_owned_replace_is_centralized(self):
        offenders=[]
        for path in (ROOT/'src/kr_book_to_audio').glob('*.py'):
            if path.name=='durable_io.py': continue
            if 'os.replace(' in path.read_text(encoding='utf-8'):
                offenders.append(path.name)
        self.assertEqual(offenders,[])

    def test_sqlite_state_engine_is_public_and_documented(self):
        self.assertTrue((ROOT/'src/kr_book_to_audio/job_state.py').exists())
        readme=(ROOT/'README.md').read_text(encoding='utf-8')
        self.assertIn('job_state.sqlite3',readme)
        self.assertIn('job_manifest.json',readme)
