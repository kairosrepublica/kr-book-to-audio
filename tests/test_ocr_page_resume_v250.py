import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kr_book_to_audio.ocr import OCRAnalysis, run_recommended_ocr


class RecordingProvider:
    page_checkpoint_capable = True
    def __init__(self, *, fail_page=None):
        self.fail_page = fail_page
        self.calls = []
    def recognize_pdf_to_text(self, source, *, language, output_dir, pages=None, progress=None):
        page = int(list(pages or [0])[0])
        self.calls.append(page)
        if page == self.fail_page:
            raise RuntimeError(f'page-{page}-boom')
        return f'page {page} text'


class OCRPageResumeV250Tests(unittest.TestCase):
    def test_interrupted_run_preserves_completed_pages_and_resumes_from_first_missing_page(self):
        from contextlib import nullcontext
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        import json
        import tempfile
        from kr_book_to_audio import ocr

        class PageProvider:
            page_checkpoint_capable = True
            def __init__(self):
                self.fail_page_two = True
                self.calls = []
            def recognize_pdf_to_text(self, source, *, language, output_dir, pages=None, progress=None):
                page = int(list(pages or [0])[0])
                self.calls.append(page)
                if page == 2 and self.fail_page_two:
                    raise RuntimeError('page-2-boom')
                return f'text-page-{page}'

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'book.pdf'
            source.write_bytes(b'%PDF fixture')
            output = root / 'ocr'
            analysis = SimpleNamespace(recommended_provider='fixture-provider', language='chi_sim', sample_pages=[1, 2, 3])
            provider = PageProvider()
            with (
                patch.object(ocr, 'get_ocr_provider', return_value=provider),
                patch.object(ocr, 'diagnose', return_value={'pages': 3}),
                patch.object(ocr, 'keep_computer_awake', return_value=nullcontext()),
                patch.object(ocr.time, 'sleep', return_value=None),
            ):
                first_target = ocr.run_recommended_ocr(source, analysis, output_dir=output, keep_awake=False)
            first_state = json.loads((output / '_ocr_execution.json').read_text(encoding='utf-8'))
            self.assertEqual(provider.calls, [1, 2, 3])
            self.assertEqual(first_state['completed_pages'], [1, 3])
            self.assertEqual(first_state['failed_pages'], [2])
            self.assertIn('[OCR FAILED PAGE 2]', first_target.read_text(encoding='utf-8'))

            provider.fail_page_two = False
            provider.calls = []
            with (
                patch.object(ocr, 'get_ocr_provider', return_value=provider),
                patch.object(ocr, 'diagnose', return_value={'pages': 3}),
                patch.object(ocr, 'keep_computer_awake', return_value=nullcontext()),
                patch.object(ocr.time, 'sleep', return_value=None),
            ):
                second_target = ocr.retry_failed_ocr_pages(source, analysis, output_dir=output, keep_awake=False)
            second_state = json.loads((output / '_ocr_execution.json').read_text(encoding='utf-8'))
            self.assertEqual(provider.calls, [2])
            self.assertEqual(second_state['status'], 'completed')
            self.assertEqual(second_state['completed_pages'], [1, 2, 3])
            self.assertEqual(second_state['failed_pages'], [])
            self.assertNotIn('[OCR FAILED PAGE 2]', second_target.read_text(encoding='utf-8'))
            self.assertIn('text-page-2', second_target.read_text(encoding='utf-8'))

    def test_same_path_with_changed_pdf_bytes_does_not_reuse_stale_page_checkpoints(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / 'scan.pdf'; source.write_bytes(b'%PDF-first')
            analysis = OCRAnalysis('required', 'pdf', 'english', 'fake', 'test', [1, 2], {}, 0)
            first = RecordingProvider()
            with patch('kr_book_to_audio.ocr.get_ocr_provider', return_value=first), patch('kr_book_to_audio.ocr.diagnose', return_value={'pages': 2}):
                run_recommended_ocr(source, analysis, output_dir=root / 'out', provider_id='fake', keep_awake=False)
            source.write_bytes(b'%PDF-second')
            second = RecordingProvider()
            progress = []
            with patch('kr_book_to_audio.ocr.get_ocr_provider', return_value=second), patch('kr_book_to_audio.ocr.diagnose', return_value={'pages': 2}):
                run_recommended_ocr(source, analysis, output_dir=root / 'out', provider_id='fake', keep_awake=False, progress=progress.append)
            self.assertEqual(second.calls, [1, 2])
            self.assertFalse(any(item['state'] == 'ocr-page-reused' for item in progress))


if __name__ == '__main__':
    unittest.main()
