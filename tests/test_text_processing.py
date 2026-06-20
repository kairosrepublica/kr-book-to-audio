import json
import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.text_processing import analyze_cleanup, apply_dictionary, chunk_text, clean_text, detect_article_boundaries, load_dictionary, normalize_cjk, n_cjk

class TextProcessingTests(unittest.TestCase):
    def test_cjk_spacing_normalization_preserves_ascii_spaces(self):
        self.assertEqual(normalize_cjk('大 数 据 S&P 500 增 长。'), '大数据S&P 500增长。')
    def test_running_header_removed(self):
        raw = '章标题\n正文第一句。\f章标题\n正文第二句。\f章标题\n正文第三句。'
        cleaned, stats = clean_text(raw)
        self.assertNotIn('章标题', cleaned)
        self.assertEqual(stats['residual_intra_cjk_spaces'], 0)

    def test_preserve_paragraph_breaks_keeps_heading_separate_from_body(self):
        raw = '标题没有句号\n\n正文第一句。\n\n第一，二零二一年八月十四日\n\n回报递增的事物。'
        cleaned, stats = clean_text(raw, preserve_paragraph_breaks=True)
        self.assertIn('标题没有句号\n\n正文第一句。', cleaned)
        self.assertIn('第一，二零二一年八月十四日\n\n回报递增的事物。', cleaned)
        self.assertTrue(stats['preserve_paragraph_breaks'])


    def test_preserve_paragraph_breaks_keeps_mixed_language_paragraph(self):
        raw = '标题\n\n可参见 Brian Arthur in Harvard Business Review 1996.\n\n正文。'
        cleaned, stats = clean_text(raw, preserve_paragraph_breaks=True)
        self.assertIn('Brian Arthur', cleaned)
        self.assertIn('Harvard Business Review', cleaned)
        self.assertTrue(stats['preserve_paragraph_breaks'])

    def test_structure_aware_preserves_confident_article_title_and_section_heading(self):
        raw = '随感合集 – 回报递增、时间压力\n\n以下为 2021年八月间笔者在微博号发表。\n\n第一，二零二一年八月十四日\n\n回报递增的事物。'
        cleaned, stats = clean_text(raw, layout_mode='structure-aware')
        self.assertIn('随感合集–回报递增、时间压力\n\n以下为2021年八月间笔者在微博号发表。', cleaned)
        self.assertIn('第一，二零二一年八月十四日\n\n回报递增的事物。', cleaned)
        self.assertEqual(stats['layout_mode'], 'structure-aware')
        self.assertGreaterEqual(stats['structural_breaks_preserved'], 2)

    def test_structure_aware_reflows_incomplete_broken_paragraph(self):
        raw = '这是一个没有结束的段落\n\n继续这个段落。'
        cleaned, stats = clean_text(raw, layout_mode='structure-aware')
        self.assertIn('这是一个没有结束的段落继续这个段落。', cleaned)
        self.assertEqual(stats['artificial_breaks_reflowed'], 1)

    def test_standard_mode_keeps_legacy_heading_join_behavior(self):
        cleaned, stats = clean_text('章标题\n\n正文第一句。', layout_mode='standard')
        self.assertIn('章标题正文第一句。', cleaned)
        self.assertEqual(stats['layout_mode'], 'standard')

    def test_dictionary_preview(self):
        rendered, preview = apply_dictionary('重庆重庆', [{'find': '重庆', 'replace': '重 庆', 'enabled': True}])
        self.assertEqual(rendered, '重 庆重 庆')
        self.assertEqual(preview[0]['count'], 2)

    def test_article_provenance_is_not_high_confidence_junk(self):
        report = analyze_cleanup('本文最初于2021年5月17日在笔者的微信公众号上发表。')
        junk = report['repeated_headers_and_junk']
        self.assertEqual(junk['count'], 0)
        self.assertEqual(junk['high_confidence'], [])

    def test_dictionary_loader_accepts_replacements_object(self):
        with tempfile.TemporaryDirectory() as td:
            dictionary = Path(td) / 'dictionary.json'
            dictionary.write_text(json.dumps({'replacements': [{'find': '中文', 'replace': '中 文'}]}, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(load_dictionary(dictionary), [{'find': '中文', 'replace': '中 文', 'enabled': True}])

    def test_dictionary_loader_accepts_direct_lexicon_entries(self):
        with tempfile.TemporaryDirectory() as td:
            dictionary = Path(td) / 'lexicon.json'
            dictionary.write_text(json.dumps({
                'language': 'zh-CN',
                'acronyms': [{'source': 'AI', 'spoken': '人工智能'}],
                'units': [{'source': '°C', 'spoken': '摄氏度'}],
                'phrase_pronunciations': [{'grapheme': '音乐', 'pinyin': 'yin1 yue4'}],
            }, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(load_dictionary(dictionary), [
                {'find': 'AI', 'replace': '人工智能', 'enabled': True},
                {'find': '°C', 'replace': '摄氏度', 'enabled': True},
            ])

    def test_dictionary_loader_rejects_malformed_replacements(self):
        with tempfile.TemporaryDirectory() as td:
            dictionary = Path(td) / 'dictionary.json'
            dictionary.write_text(json.dumps({'replacements': {'find': 'AI', 'replace': 'A I'}}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'replacements must be a list'):
                load_dictionary(dictionary)

    def test_general_prose_mode_preserves_english(self):
        cleaned, stats = clean_text('This is an English sentence.\n\nThis is another paragraph.')
        self.assertIn('English sentence', cleaned)
        self.assertEqual(stats['language_mode'], 'english')
    def test_oversized_english_paragraph_is_split(self):
        parts = chunk_text('a' * 250 + '.', max_cjk=100)
        self.assertEqual([len(p) for p in parts], [100, 100, 51])
    def test_oversized_paragraph_is_split(self):
        text = '中' * 250 + '。'
        parts = chunk_text(text, max_cjk=100)
        self.assertEqual([n_cjk(p) for p in parts], [100, 100, 50])

    def test_article_boundaries_preferred_for_part_splitting(self):
        article1 = '文章一\n\n本文最初发布。\n\n' + ('一' * 80) + '。'
        article2 = '文章二\n\n本文最初发布。\n\n' + ('二' * 80) + '。'
        text = article1 + '\n\n' + article2
        parts = chunk_text(text, max_cjk=120)
        self.assertEqual(len(parts), 2)
        self.assertIn('文章一', parts[0])
        self.assertNotIn('文章二', parts[0])
        self.assertIn('文章二', parts[1])
        self.assertEqual(detect_article_boundaries([p.strip() for p in text.split('\n\n') if p.strip()]), [0, 3])

if __name__ == '__main__': unittest.main()
