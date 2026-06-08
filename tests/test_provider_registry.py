import unittest
from kr_book_to_audio.audio import audio_signature
from kr_book_to_audio.providers import OCR_PROVIDER_SPECS, TTS_PROVIDER_SPECS, ProviderUnavailable, get_tts_provider, provider_registry_snapshot


class ProviderRegistryTests(unittest.TestCase):
    def test_edge_tts_is_only_enabled_tts_provider_and_api_slots_are_reserved(self):
        self.assertTrue(TTS_PROVIDER_SPECS['edge-tts'].enabled)
        self.assertFalse(TTS_PROVIDER_SPECS['azure-speech-api'].enabled)
        self.assertFalse(TTS_PROVIDER_SPECS['openai-tts-api'].enabled)
        self.assertFalse(TTS_PROVIDER_SPECS['custom-http-tts-api'].enabled)

    def test_ocr_registry_contains_local_and_external_api_slots(self):
        for provider_id in ('native-text', 'paddleocr-ppocrv5', 'tesseract-local', 'ocrmypdf-tesseract', 'openai-vision-api', 'claude-vision-api', 'custom-http-ocr-api'):
            self.assertIn(provider_id, OCR_PROVIDER_SPECS)
        self.assertFalse(OCR_PROVIDER_SPECS['openai-vision-api'].enabled)
        self.assertFalse(OCR_PROVIDER_SPECS['claude-vision-api'].enabled)

    def test_audio_signature_changes_with_provider_id(self):
        edge = audio_signature(provider_id='edge-tts', voice='voice', rate='+0%')
        api = audio_signature(provider_id='openai-tts-api', voice='voice', rate='+0%')
        self.assertNotEqual(edge, api)

    def test_reserved_tts_api_provider_cannot_run(self):
        provider = get_tts_provider('openai-tts-api')
        with self.assertRaises(ProviderUnavailable):
            provider.synthesize('text', __import__('pathlib').Path('x.mp3'), voice='v', rate='+0%', pitch='+0Hz', volume='+0%')

    def test_registry_snapshot_is_serializable(self):
        snapshot = provider_registry_snapshot()
        self.assertIn('tts', snapshot)
        self.assertIn('ocr', snapshot)


if __name__ == '__main__': unittest.main()
