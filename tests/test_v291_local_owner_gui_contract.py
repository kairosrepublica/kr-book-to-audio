import unittest
from pathlib import Path
from kr_book_to_audio.local_ocr import LocalOCRFoundation
from kr_book_to_audio.ocr_workflow_ui import OCR_BUTTON_OPTIONAL, derive_ocr_ui_plan
from kr_book_to_audio.workflow_completion_ui import COLOR_OPTIONAL
from kr_book_to_audio.paddleocr_worker_script import PADDLEOCR_WORKER_SCRIPT

ROOT=Path(__file__).resolve().parents[1]

class V291OwnerGuiCorrectionTests(unittest.TestCase):
    def test_reload_is_compact_and_exactly_named(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn("self.reload_button = button(workspace, 'Reload book'", source)
    def test_audition_snapshot_excludes_keep_awake(self):
        gui=(ROOT/'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertIn('def _audition_request_snapshot',gui)
        self.assertIn('return dict(self._current_speech_controls())',gui)
        marker=gui.split('def audition(self)',1)[1].split('def _play',1)[0]
        self.assertNotIn('_speech_request_snapshot()',marker)
        self.assertIn('Voice preview audio was not generated.',marker)
    def test_advanced_is_rightmost_neutral_and_row_tip_is_removed(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn("'Advanced recovery'", source)
        self.assertIn("'Advanced'", source)
        self.assertNotIn('Advanced settings row tip', source)
    def test_optional_palette_is_soft_blue(self):
        self.assertEqual(OCR_BUTTON_OPTIONAL,'#D6ECF0')
        self.assertEqual(COLOR_OPTIONAL,'#D6ECF0')
        for relative in ['src/kr_book_to_audio/ocr_workflow_ui.py','src/kr_book_to_audio/workflow_completion_ui.py','src/kr_book_to_audio/gui.py']:
            self.assertNotIn('#fff3cd',(ROOT/relative).read_text(encoding='utf-8'))
    def test_worker_stdout_receipt_is_ascii_safe(self):
        self.assertIn("ensure_ascii=True",PADDLEOCR_WORKER_SCRIPT)
        self.assertIn("sys.stdout.reconfigure(encoding='utf-8'",PADDLEOCR_WORKER_SCRIPT)
    def test_offline_env_forces_utf8(self):
        foundation=LocalOCRFoundation(Path('runtime'),Path('archive'))
        env=foundation.offline_env()
        self.assertEqual(env['PYTHONUTF8'],'1')
        self.assertEqual(env['PYTHONIOENCODING'],'utf-8')
    def test_gui_error_is_sanitized(self):
        gui=(ROOT/'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertIn('sanitize_user_error',gui)
        self.assertIn('Diagnostics were preserved',gui)
    def test_future_repair_refreshes_stale_worker(self):
        setup=(ROOT/'src/kr_book_to_audio/local_ocr_setup.py').read_text(encoding='utf-8')
        self.assertIn('def _write_worker_if_stale',setup)
        self.assertIn('_write_worker_if_stale(foundation.paddle_worker, PADDLEOCR_WORKER_SCRIPT)',setup)
    def test_parent_decodes_worker_stream_as_utf8(self):
        providers=(ROOT/'src/kr_book_to_audio/providers.py').read_text(encoding='utf-8')
        paddle=providers.split("class PaddleOCRProvider",1)[1].split("class TesseractOCRProvider",1)[0]
        self.assertIn("encoding='utf-8'",paddle)
        self.assertIn("errors='replace'",paddle)

if __name__=='__main__': unittest.main()
