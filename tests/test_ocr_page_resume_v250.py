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
    def recognize_pdf_to_text(self, source, *, language, output_dir, pages=None):
        page = int(list(pages or [0])[0])
        self.calls.append(page)
        if page == self.fail_page:
            raise RuntimeError(f'page-{page}-boom')
        return f'page {page} text'


class OCRPageResumeV250Tests(unittest.TestCase):
    def test_interrupted_run_preserves_completed_pages_and_resumes_from_first_missing_page(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / 'scan.pdf'; source.write_bytes(b'%PDF')
            analysis = OCRAnalysis('required', 'pdf', 'english', 'fake', 'test', [1, 2, 3], {}, 0)
            first = RecordingProvider(fail_page=2)
            with patch('kr_book_to_audio.ocr.get_ocr_provider', return_value=first), patch('kr_book_to_audio.ocr.diagnose', return_value={'pages': 3}):
                with self.assertRaisesRegex(RuntimeError, 'page-2-boom'):
                    run_recommended_ocr(source, analysis, output_dir=root / 'out', provider_id='fake', keep_awake=False)
            self.assertEqual(first.calls, [1, 2])
            second = RecordingProvider()
            progress = []
            with patch('kr_book_to_audio.ocr.get_ocr_provider', return_value=second), patch('kr_book_to_audio.ocr.diagnose', return_value={'pages': 3}):
                output = run_recommended_ocr(source, analysis, output_dir=root / 'out', provider_id='fake', keep_awake=False, progress=progress.append)
            self.assertEqual(second.calls, [2, 3])
            self.assertEqual(output.read_text(encoding='utf-8'), 'page 1 text\n\npage 2 text\n\npage 3 text\n')
            self.assertTrue(any(item['state'] == 'ocr-page-reused' and item['page'] == 1 for item in progress))
            self.assertEqual(progress[-1]['state'], 'ocr-completed')
            self.assertIn('average_seconds_per_page', progress[-1])
            self.assertEqual(progress[-1]['estimated_remaining_seconds'], 0.0)
            self.assertEqual(progress[-1]['last_completed_page'], 3)

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
