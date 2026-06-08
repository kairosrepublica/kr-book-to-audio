import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kr_book_to_audio.ocr import OCRAnalysis, run_recommended_ocr


class FakeProvider:
    page_checkpoint_capable = True
    def recognize_pdf_to_text(self, source, *, language, output_dir, pages=None):
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
        class FailingProvider(FakeProvider):
            def recognize_pdf_to_text(self, source, *, language, output_dir, pages=None):
                raise RuntimeError('boom')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / 'scan.pdf'; source.write_bytes(b'%PDF')
            analysis = OCRAnalysis('required', 'pdf', 'chinese', 'fake', 'test', [1], {}, 0)
            with patch('kr_book_to_audio.ocr.get_ocr_provider', return_value=FailingProvider()):
                with self.assertRaisesRegex(RuntimeError, 'boom'):
                    run_recommended_ocr(source, analysis, output_dir=root / 'out', provider_id='fake', keep_awake=False)
            state = json.loads((root / 'out' / '_ocr_execution.json').read_text(encoding='utf-8'))
            self.assertEqual(state['status'], 'interrupted-or-failed')


if __name__ == '__main__': unittest.main()
