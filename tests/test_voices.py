import unittest
from kr_book_to_audio.voices import filter_voices

VOICES = [
    {'short_name': 'zh-CN-YunyangNeural', 'locale': 'zh-CN'},
    {'short_name': 'en-US-GuyNeural', 'locale': 'en-US'},
    {'short_name': 'fr-FR-HenriNeural', 'locale': 'fr-FR'},
]

class VoiceFilterTests(unittest.TestCase):
    def test_chinese_profile_filters_zh(self):
        self.assertEqual([v['short_name'] for v in filter_voices(VOICES, 'chinese')], ['zh-CN-YunyangNeural'])
    def test_english_profile_filters_en(self):
        self.assertEqual([v['short_name'] for v in filter_voices(VOICES, 'english')], ['en-US-GuyNeural'])
    def test_mixed_profile_includes_zh_and_en(self):
        self.assertEqual([v['short_name'] for v in filter_voices(VOICES, 'mixed')], ['zh-CN-YunyangNeural', 'en-US-GuyNeural'])
    def test_show_all_preserves_all(self):
        self.assertEqual(len(filter_voices(VOICES, 'chinese', show_all=True)), 3)

if __name__ == '__main__': unittest.main()
