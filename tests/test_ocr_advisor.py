import unittest
from pathlib import Path
from unittest.mock import patch
from kr_book_to_audio.ocr import OCRAnalysis, analyze_source, detect_language, quality_score

class OCRAdvisorTests(unittest.TestCase):
    def test_language_detection(self):
        self.assertEqual(detect_language('中文内容' * 10), 'chinese')
        self.assertEqual(detect_language('English prose ' * 10), 'english')
        self.assertEqual(detect_language(('中文' * 20) + ('English' * 20)), 'mixed')

    def test_quality_score_zero_for_empty(self):
        self.assertEqual(quality_score(''), 0)

    @patch('kr_book_to_audio.ocr.discover_ocr_capabilities')
    @patch('kr_book_to_audio.ocr.diagnose')
    def test_native_source_bypasses_ocr(self, diagnose, discover):
        diagnose.return_value = {'format': 'epub', 'extractable': True, 'needs_ocr': False}
        discover.return_value = {}
        report = analyze_source(Path('book.epub'))
        self.assertEqual(report.status, 'not-applicable')
        self.assertEqual(report.recommended_provider, 'native-text')

    @patch('kr_book_to_audio.ocr._sample_pdf_text', return_value='中文内容' * 10)
    @patch('kr_book_to_audio.ocr.discover_ocr_capabilities')
    @patch('kr_book_to_audio.ocr.diagnose')
    def test_scanned_chinese_pdf_recommends_paddle_when_available(self, diagnose, discover, sample):
        diagnose.return_value = {'format': 'pdf', 'extractable': False, 'needs_ocr': True, 'sample_pages': [1, 3, 5], 'reason': 'scan'}
        discover.return_value = {'paddleocr-ppocrv5': {'available': True}}
        report = analyze_source(Path('book.pdf'))
        self.assertEqual(report.status, 'required')
        self.assertEqual(report.language, 'chinese')
        self.assertEqual(report.recommended_provider, 'paddleocr-ppocrv5')

    @patch('kr_book_to_audio.ocr._sample_pdf_text', return_value='English prose ' * 20)
    @patch('kr_book_to_audio.ocr.discover_ocr_capabilities')
    @patch('kr_book_to_audio.ocr.diagnose')
    def test_scanned_english_pdf_falls_back_to_tesseract(self, diagnose, discover, sample):
        diagnose.return_value = {'format': 'pdf', 'extractable': False, 'needs_ocr': True, 'sample_pages': [1], 'reason': 'scan'}
        discover.return_value = {'paddleocr-ppocrv5': {'available': False}, 'tesseract-local': {'available': True}}
        report = analyze_source(Path('book.pdf'))
        self.assertEqual(report.language, 'english')
        self.assertEqual(report.recommended_provider, 'tesseract-local')

    @patch('kr_book_to_audio.ocr._sample_pdf_text', return_value='Readable text ' * 50)
    @patch('kr_book_to_audio.ocr.discover_ocr_capabilities', return_value={})
    @patch('kr_book_to_audio.ocr.diagnose')
    def test_good_pdf_reports_ocr_not_needed(self, diagnose, discover, sample):
        diagnose.return_value = {'format': 'pdf', 'extractable': True, 'needs_ocr': False, 'sample_pages': [1]}
        report = analyze_source(Path('book.pdf'))
        self.assertEqual(report.status, 'not-needed')
        self.assertEqual(report.recommended_provider, 'native-text')

    def test_tesseract_chinese_recommendation_requires_chi_sim_pack(self):
        from kr_book_to_audio.ocr import _recommend_provider
        caps = {'paddleocr-ppocrv5': {'available': False}, 'tesseract-local': {'available': True, 'details': {'languages': ['eng']}}}
        self.assertIsNone(_recommend_provider('chinese', caps))
        caps['tesseract-local']['details']['languages'].append('chi_sim')
        self.assertEqual(_recommend_provider('chinese', caps), 'tesseract-local')

if __name__ == '__main__': unittest.main()
