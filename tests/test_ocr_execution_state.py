import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kr_book_to_audio.ocr import OCRAnalysis, run_recommended_ocr


class FakeProvider:
    page_checkpoint_capable = True
    def recognize_pdf_to_text(self, source, *, language, output_dir, pages=None, progress=None):
        return '中文识别内容。'


class OCRExecutionStateTests(unittest.TestCase):
    def test_ocr_run_writes_completed_execution_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / 'scan.pdf'; source.write_bytes(b'%PDF')
            analysis = OCRAnalysis('required', 'pdf', 'chinese', 'fake', 'test', [1], {}, 0)
            with patch('kr_book_to_audio.ocr.get_ocr_provider', return_value=FakeProvider()):
                output = run_recommended_ocr(source, analysis, output_dir=root / 'out', provider_id='fake', keep_awake=False)
            state = json.loads((root / 'out' / '_ocr_execution.json').read_text(encoding='utf-8'))
            self.assertEqual(state['status'], 'completed')
            self.assertTrue(state['page_checkpoint_capable'])
            self.assertEqual(Path(state['output']), output)

    def test_ocr_run_writes_failure_state(self):
        from contextlib import nullcontext
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        import json
        import tempfile
        from kr_book_to_audio import ocr

        class FailingProvider:
            page_checkpoint_capable = True
            def recognize_pdf_to_text(self, source, *, language, output_dir, pages=None, progress=None):
                raise RuntimeError('boom')

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'book.pdf'
            source.write_bytes(b'%PDF fixture')
            output = root / 'ocr'
            analysis = SimpleNamespace(recommended_provider='fixture-provider', language='chi_sim', sample_pages=[1])
            with (
                patch.object(ocr, 'get_ocr_provider', return_value=FailingProvider()),
                patch.object(ocr, 'diagnose', return_value={'pages': 1}),
                patch.object(ocr, 'keep_computer_awake', return_value=nullcontext()),
                patch.object(ocr.time, 'sleep', return_value=None),
            ):
                target = ocr.run_recommended_ocr(source, analysis, output_dir=output, keep_awake=False)
            state = json.loads((output / '_ocr_execution.json').read_text(encoding='utf-8'))
            self.assertEqual(state['status'], 'completed-with-page-failures')
            self.assertEqual(state['completed_pages'], [])
            self.assertEqual(state['failed_pages'], [1])
            self.assertIn('[OCR FAILED PAGE 1]', target.read_text(encoding='utf-8'))


if __name__ == '__main__': unittest.main()
