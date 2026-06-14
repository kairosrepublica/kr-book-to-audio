from pathlib import Path
import unittest
from kr_book_to_audio.local_ocr import LocalOCRFoundation

ROOT = Path(__file__).resolve().parents[1]


class V292OfflineVisibilityClosureTests(unittest.TestCase):
    def test_fast_local_is_recommended_before_high_accuracy(self):
        source = (ROOT / 'src/kr_book_to_audio/ocr.py').read_text(encoding='utf-8')
        self.assertIn("('paddleocr-ppocrv5-mobile', 'paddleocr-ppocrv5')", source)

    def test_gui_uses_local_model_language_and_activity_heartbeat(self):
        gui = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn('language: {analysis.language}', gui)
        self.assertIn('def _ocr_progress_tick(self, token: int) -> None:', gui)
        self.assertIn('heartbeat_due = from_tick', gui)
        self.assertIn('KR_B2A_OCR_HEARTBEAT_SECONDS', gui)
        self.assertIn("getattr(self, '_last_ocr_heartbeat_at'", gui)
        self.assertIn("Full OCR | page {source_page} / {source_total}", gui)
        self.assertIn("current page {current_pct}%", gui)
        self.assertIn("whole book {overall_pct:.1f}%", gui)

    def test_offline_ocr_scrubs_proxy_variables(self):
        foundation = LocalOCRFoundation(Path('runtime'), Path('archive'))
        env = foundation.offline_env({'HTTP_PROXY': 'http://proxy.invalid', 'HTTPS_PROXY': 'http://proxy.invalid'})
        self.assertEqual(env['KR_B2A_OCR_OFFLINE_ONLY'], '1')
        self.assertEqual(env['NO_PROXY'], '*')
        self.assertNotIn('HTTP_PROXY', env)
        self.assertNotIn('HTTPS_PROXY', env)

    def test_paddle_receipts_record_offline_mode_and_native_exit_hex(self):
        source = (ROOT / 'src/kr_book_to_audio/providers.py').read_text(encoding='utf-8')
        self.assertIn("'offline_mode_enforced': True", source)
        self.assertIn("'returncode_hex': self._exit_hex(returncode)", source)
        self.assertIn("0xc0000005", source)

    def test_prejob_diagnostics_and_top_level_reload_remain_present(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn('export_prejob_ocr_diagnostic_zip', source)
        self.assertIn("self.reload_button = button(workspace, 'Reload book'", source)
        self.assertIn("'Open diagnostics folder'", source)


if __name__ == '__main__':
    unittest.main()
