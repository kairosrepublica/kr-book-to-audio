import tempfile
import unittest
from pathlib import Path

from kr_book_to_audio.document_blocks import DocumentBlock
from kr_book_to_audio.extractors import extract_epub_blocks
from kr_book_to_audio.pipeline import prepare_job
from kr_book_to_audio.text_processing import clean_document_blocks


class V330TextEngineTests(unittest.TestCase):
    def test_document_block_engine_preserves_epub_headings_and_paragraphs(self):
        blocks = [
            DocumentBlock('heading', 'Chapter One', source='epub_html', level=1),
            DocumentBlock('heading', 'The New Human Agenda', source='epub_html', level=2),
            DocumentBlock('paragraph', 'At the dawn of the third millennium, humanity wakes up.', source='epub_html'),
        ]
        cleaned, stats = clean_document_blocks(blocks, layout_mode='structure-aware')
        self.assertIn('Chapter One\n\nThe New Human Agenda\n\nAt the dawn', cleaned)
        self.assertEqual(stats['engine'], 'document-block-v1')
        self.assertEqual(stats['source_block_types']['heading'], 2)

    def test_pdf_block_engine_removes_page_footer_and_reflows_wrapped_chinese(self):
        blocks = [
            DocumentBlock('paragraph', '从2022年初开始，中国经济快速陷入资产负债表衰退，出现螺旋下降的', page=1, source='pdf_native'),
            DocumentBlock('footer', 'https://example.com/x 2024/7/7 10:29', page=1, source='pdf_native'),
            DocumentBlock('page_number', '页码： 1/54', page=1, source='pdf_native'),
            DocumentBlock('paragraph', '通货紧缩。', page=2, source='pdf_native'),
        ]
        cleaned, stats = clean_document_blocks(blocks, layout_mode='structure-aware')
        self.assertIn('出现螺旋下降的通货紧缩。', cleaned)
        self.assertNotIn('https://example.com', cleaned)
        self.assertGreaterEqual(stats['noise_blocks_removed'], 2)

    def test_prepare_job_uses_document_block_engine_for_plain_source(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'book.txt'
            source.write_text('标题\n\n正文第一句。\n\n第二节\n\n正文第二句。', encoding='utf-8')
            job = prepare_job(source, work_root=Path(td) / 'work', export_root=Path(td) / 'out', layout_mode='structure-aware')
            manifest = job.manifest.read_text(encoding='utf-8')
            proofread = job.proofread.read_text(encoding='utf-8')
            self.assertIn('document-block-v1', manifest)
            self.assertIn('标题\n\n正文第一句。', proofread)


if __name__ == '__main__':
    unittest.main()
