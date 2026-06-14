from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V295Pre30ClosureContractTests(unittest.TestCase):
    def test_ui_modules_exist(self):
        self.assertTrue((ROOT / 'src/kr_book_to_audio/ui_v295.py').is_file())
        self.assertTrue((ROOT / 'src/kr_book_to_audio/edge_voice_samples.py').is_file())

    def test_gui_uses_stable_layout_and_dictionary_default(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn("self.root.geometry('1580x1260')", source)
        self.assertIn('self.root.minsize(1480, 1260)', source)
        self.assertIn("('Pronunciation dictionary', self.dictionary", source)
        self.assertIn("card(content, 'Source and storage'", source)

    def test_ocr_safe_local_contract(self):
        providers = (ROOT / 'src/kr_book_to_audio/providers.py').read_text(encoding='utf-8')
        worker = (ROOT / 'src/kr_book_to_audio/paddleocr_worker_script.py').read_text(encoding='utf-8')
        ocr = (ROOT / 'src/kr_book_to_audio/ocr.py').read_text(encoding='utf-8')
        self.assertIn("KR_B2A_PADDLEOCR_PAGE_TIMEOUT_SECONDS', '120'", providers)
        self.assertIn("KR_B2A_OCR_CPU_THREADS", providers)
        self.assertIn("cpu_threads = max(1, min(4", worker)
        self.assertIn("failed_pages", ocr)
        self.assertIn("ocr-page-failed-continued", ocr)
        self.assertIn("_ascii_staging", providers)
        self.assertNotIn("chi_sim_vert", providers)

    def test_edge_samples_are_explicit(self):
        gui = (ROOT / 'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        cache = (ROOT / 'src/kr_book_to_audio/edge_voice_samples.py').read_text(encoding='utf-8')
        self.assertIn("Download / refresh Edge voice samples", gui)
        self.assertIn("refresh_all", cache)
        self.assertIn("cached_path", cache)

    def test_kr_palette_only(self):
        ui = (ROOT / 'src/kr_book_to_audio/ui_v295.py').read_text(encoding='utf-8')
        self.assertIn("KR_YUE_BAI = '#D6ECF0'", ui)
        self.assertIn("KR_XIANG_SE = '#F0C239'", ui)
        self.assertIn("DIGITAL_UI_FORBIDDEN", ui)


if __name__ == '__main__':
    unittest.main()
