import unittest
from kr_book_to_audio.text_processing import apply_dictionary, chunk_text, clean_text, normalize_cjk, n_cjk

class TextProcessingTests(unittest.TestCase):
    def test_cjk_spacing_normalization_preserves_ascii_spaces(self):
        self.assertEqual(normalize_cjk('大 数 据 S&P 500 增 长。'), '大数据S&P 500增长。')
    def test_running_header_removed(self):
        raw = '章标题\n正文第一句。\f章标题\n正文第二句。\f章标题\n正文第三句。'
        cleaned, stats = clean_text(raw)
        self.assertNotIn('章标题', cleaned)
        self.assertEqual(stats['residual_intra_cjk_spaces'], 0)
    def test_dictionary_preview(self):
        rendered, preview = apply_dictionary('重庆重庆', [{'find': '重庆', 'replace': '重 庆', 'enabled': True}])
        self.assertEqual(rendered, '重 庆重 庆')
        self.assertEqual(preview[0]['count'], 2)
    def test_general_prose_mode_preserves_english(self):
        cleaned, stats = clean_text('This is an English sentence.\n\nThis is another paragraph.')
        self.assertIn('English sentence', cleaned)
        self.assertEqual(stats['language_mode'], 'general-prose')
    def test_oversized_english_paragraph_is_split(self):
        parts = chunk_text('a' * 250 + '.', max_cjk=100)
        self.assertEqual([len(p) for p in parts], [100, 100, 51])
    def test_oversized_paragraph_is_split(self):
        text = '中' * 250 + '。'
        parts = chunk_text(text, max_cjk=100)
        self.assertEqual([n_cjk(p) for p in parts], [100, 100, 50])

if __name__ == '__main__': unittest.main()
