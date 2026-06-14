from __future__ import annotations
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V296DependencyAwareCollectAllTests(unittest.TestCase):
    def test_product_palette_has_no_retired_active_runtime_literals(self):
        retired = {'#efefef','#f8f9fa','#f4a261','#dbeafe','#f8d7da','#d9f2d9','#e8f5e9','#006400','#1e3a5f','#666666','#8b0000','#999999','#e6e6e6','#fdecec','#eef8f0'}
        for path in sorted((ROOT / 'src').rglob('*.py')):
            inside_negative = False
            for line in path.read_text(encoding='utf-8').splitlines():
                if line.strip().startswith('DIGITAL_UI_FORBIDDEN'):
                    inside_negative = True
                if not inside_negative:
                    lower = line.lower()
                    for token in retired:
                        self.assertNotIn(token, lower, f'{path}: {line}')
                if inside_negative and '}' in line:
                    inside_negative = False

    def test_provider_fixture_is_offline_contract_based(self):
        source = (ROOT / 'tests' / 'test_ocr_provider_contract_v250.py').read_text(encoding='utf-8')
        self.assertIn('KR_B2A_OCR_OFFLINE_ONLY', source)
        self.assertNotIn('def capture_write(', source)

    def test_ocr_failure_continuation_remains_present(self):
        execution = (ROOT / 'tests' / 'test_ocr_execution_state.py').read_text(encoding='utf-8')
        resume = (ROOT / 'tests' / 'test_ocr_page_resume_v250.py').read_text(encoding='utf-8')
        self.assertIn('completed-with-page-failures', execution)
        self.assertIn('provider.calls, [2]', resume)

    def test_html_approved_product_contracts_are_present(self):
        gui = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        edge = (ROOT / 'src' / 'kr_book_to_audio' / 'edge_voice_samples.py').read_text(encoding='utf-8')
        ocr = (ROOT / 'src' / 'kr_book_to_audio' / 'ocr.py').read_text(encoding='utf-8')
        for token in ('Source and storage', 'Current workspace', 'Text and speech settings', 'Text process', 'Audio process', 'Run log', 'Status', 'Refresh voice samples', 'Play sample'):
            self.assertIn(token, gui)
        self.assertIn("self.root.geometry('1580x1260')", gui)
        self.assertIn('self.root.minsize(1480, 1260)', gui)
        self.assertIn("'zh':", edge)
        self.assertIn("'tr':", edge)
        self.assertIn('completed-with-page-failures', ocr)
        self.assertIn('retry_failed_ocr_pages', ocr)

if __name__ == '__main__':
    unittest.main()
