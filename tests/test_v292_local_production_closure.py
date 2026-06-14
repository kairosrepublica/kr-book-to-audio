from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import unittest

class V292LocalProductionClosureContractTests(unittest.TestCase):
    def test_prejob_diagnostics_export(self):
        source = Path('src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertIn('export_prejob_ocr_diagnostic_zip', source)
        self.assertIn('if self.job:', source)
    def test_reload_is_top_level(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn("self.reload_button = button(workspace, 'Reload book'", source)
        self.assertIn('def _invalidate_analysis_after_reload', source)

    def test_audition_unique_filename(self):
        source = Path('src/kr_book_to_audio/audio.py').read_text(encoding='utf-8')
        self.assertIn('time.time_ns()', source)
        self.assertIn('audition-{safe_voice}-{signature}-{unique}.mp3', source)
    def test_worker_run_id(self):
        source = Path('src/kr_book_to_audio/paddleocr_worker_script.py').read_text(encoding='utf-8')
        self.assertIn("run_id = str(request.get('run_id') or '').strip()", source)
        self.assertIn("'run_id': run_id", source)
    def test_provider_attempt_protocol(self):
        source = Path('src/kr_book_to_audio/providers.py').read_text(encoding='utf-8')
        self.assertIn('paddle-attempt-{run_id}', source)
        self.assertIn('response run_id mismatch', source)
        self.assertIn('returncode_hex', source)
        self.assertIn('tesseract-best-local-250dpi', source)
    def test_privacy_safe_prejob_diagnostics(self):
        source = Path('src/kr_book_to_audio/diagnostics.py').read_text(encoding='utf-8')
        tail = source[source.index('def export_prejob_ocr_diagnostic_zip'):]
        self.assertIn("generic_run_log_included': False", tail)
        self.assertNotIn("'run.log'", tail)
        self.assertNotIn("'response.json'", tail)
    def test_full_ocr_attempt_diagnostics_are_durable(self):
        source = Path('src/kr_book_to_audio/ocr.py').read_text(encoding='utf-8')
        self.assertIn("page_attempt_dir = attempts_dir / f'page-{page:04d}'", source)
        self.assertNotIn("TemporaryDirectory(prefix=f'kr-b2a-ocr-page-{page:04d}-')", source)


if __name__ == '__main__': unittest.main()
