from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V320PortoReleaseContractTests(unittest.TestCase):
    def test_public_version_is_3_2_0(self):
        init = (ROOT / 'src' / 'kr_book_to_audio' / '__init__.py').read_text(encoding='utf-8')
        pyproject = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
        self.assertIn("__version__ = '3.2.0'", init)
        self.assertIn('version = "3.2.0"', pyproject)

    def test_gui_title_uses_porto_release_version(self):
        gui = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn("self.root.title('KR Book To Audio 3.2')", gui)
        self.assertIn("title('KR Book To Audio 3.2')", gui)
        self.assertNotIn("title('KR Book To Audio 3.0')", gui)
        self.assertNotIn("self.root.title('KR Book To Audio 3.1')", gui)

    def test_porto_release_docs_and_screenshot_are_present(self):
        release_notes = ROOT / 'docs' / 'RELEASE_NOTES_PORTO_RELEASE_3_2.md'
        screenshot = ROOT / 'docs' / 'images' / 'kr_book_to_audio_porto_release_3_2_20260620.png'
        self.assertTrue(release_notes.is_file())
        self.assertTrue(screenshot.is_file())
        notes = release_notes.read_text(encoding='utf-8')
        self.assertIn('Porto Release 3.2', notes)
        self.assertIn('Kent Reis @ Porto, Portugal', notes)
        self.assertIn('Auto smart cleanup', notes)
        self.assertIn('Minimal preserve layout', notes)
        self.assertIn('Aggressive OCR cleanup', notes)


if __name__ == '__main__':
    unittest.main()
