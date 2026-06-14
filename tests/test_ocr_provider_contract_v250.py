import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kr_book_to_audio.providers import OCR_PROVIDER_SPECS, PaddleOCRProvider, TesseractOCRProvider, get_ocr_provider


class DummyFoundation:
    def paddle_ready(self, profile): return profile in {'server', 'mobile'}
    def tesseract_ready(self, profile): return profile in {'fast', 'best'}


class OCRProviderContractV250Tests(unittest.TestCase):
    def test_registry_contains_operational_profiles(self):
        for provider_id in ('paddleocr-ppocrv5', 'paddleocr-ppocrv5-mobile', 'tesseract-local', 'tesseract-local-best'):
            self.assertIn(provider_id, OCR_PROVIDER_SPECS)
            self.assertTrue(OCR_PROVIDER_SPECS[provider_id].enabled)

    def test_operational_profiles_discover_governed_runtime_not_global_path(self):
        with patch.object(PaddleOCRProvider, '_foundation', return_value=DummyFoundation()):
            self.assertTrue(PaddleOCRProvider('server').available()[0])
            self.assertTrue(PaddleOCRProvider('mobile').available()[0])
        with patch.object(TesseractOCRProvider, '_foundation', return_value=DummyFoundation()):
            self.assertTrue(TesseractOCRProvider('fast').available()[0])
            self.assertTrue(TesseractOCRProvider('best').available()[0])


    def test_tesseract_language_discovery_requests_text_mode(self):
        foundation = Mock()
        foundation.tesseract = Mock()
        foundation.tesseract.is_file.return_value = True
        foundation.tessdata.return_value = Path('C:/ocr/tessdata/fast')
        foundation.tesseract_env.return_value = {}
        completed = Mock(stdout='List of available languages in C:/ocr/tessdata/fast (4):\neng\nchi_sim\nchi_tra\nosd\n', returncode=0)
        with patch.object(TesseractOCRProvider, '_foundation', return_value=foundation), \
             patch('kr_book_to_audio.providers.run_hidden_cli', return_value=completed) as run_cli:
            languages = TesseractOCRProvider('fast').installed_languages()
        self.assertEqual(languages, {'eng', 'chi_sim', 'chi_tra', 'osd'})
        self.assertTrue(run_cli.call_args.kwargs['text'])


    def test_paddle_provider_binds_explicit_server_and_mobile_model_names(self):
        source = (Path(__file__).resolve().parents[1] / 'src' / 'kr_book_to_audio' / 'providers.py').read_text(encoding='utf-8')
        self.assertIn("f'PP-OCRv5_{self.profile}_det'", source)
        self.assertIn("f'PP-OCRv5_{self.profile}_rec'", source)
        self.assertIn("PaddleOCRProvider('mobile')", source)
        self.assertIn("KR_B2A_OCR_OFFLINE_ONLY", source)

    def test_factory_selects_expected_profiles(self):
        self.assertEqual(get_ocr_provider('paddleocr-ppocrv5').profile, 'server')
        self.assertEqual(get_ocr_provider('paddleocr-ppocrv5-mobile').profile, 'mobile')
        self.assertEqual(get_ocr_provider('tesseract-local').profile, 'fast')
        self.assertEqual(get_ocr_provider('tesseract-local-best').profile, 'best')


if __name__ == '__main__':
    unittest.main()
