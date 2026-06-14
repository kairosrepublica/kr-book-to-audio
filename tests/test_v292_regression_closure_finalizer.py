from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V292RegressionClosureFinalizerTests(unittest.TestCase):
    def test_fake_provider_fixtures_accept_progress(self):
        test_names = (
            'test_ocr_execution_state.py',
            'test_ocr_page_resume_v250.py',
            'test_ocr_workflow_v251.py',
        )
        for name in test_names:
            source = (ROOT / 'tests' / name).read_text(encoding='utf-8')
            self.assertIn('progress=None', source, name)

    def test_provider_contract_matches_offline_worker_shape(self):
        source = (ROOT / 'tests' / 'test_ocr_provider_contract_v250.py').read_text(encoding='utf-8')
        self.assertIn("KR_B2A_OCR_OFFLINE_ONLY", source)
        self.assertIn("f'PP-OCRv5_{self.profile}_det'", source)
        self.assertIn("f'PP-OCRv5_{self.profile}_rec'", source)

    def test_tesseract_attempt_label_is_current(self):
        source = (ROOT / 'tests' / 'test_v292_local_production_closure.py').read_text(encoding='utf-8')
        self.assertIn("self.assertIn('tesseract-best-local-250dpi', source)", source)
        self.assertNotIn("self.assertIn('tesseract-best-250dpi', source)", source)

    def test_product_visibility_offline_features_remain_present(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        for token in ('Install / repair local OCR foundation', 'Open OCR resource folder', 'Export diagnostic ZIP', 'Open diagnostics folder'):
            self.assertIn(token, source)


if __name__ == '__main__':
    unittest.main()
