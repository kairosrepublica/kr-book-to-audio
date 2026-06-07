import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from kr_book_to_audio.extractors import _decode_stdout, book_title, diagnose, extract


class WindowsPdfEncodingTests(unittest.TestCase):
    def test_utf8_chinese_bytes_decode_without_windows_text_mode(self):
        self.assertEqual(_decode_stdout('标题：逆潮'.encode('utf-8')), '标题：逆潮')

    def test_none_stdout_decodes_to_empty_string(self):
        self.assertEqual(_decode_stdout(None), '')

    def test_book_title_uses_chinese_utf8_metadata(self):
        payload = SimpleNamespace(stdout='Title: 见证逆潮\nPages: 12\n'.encode('utf-8'), returncode=0)
        with patch('kr_book_to_audio.extractors.require_command'), patch('kr_book_to_audio.extractors.subprocess.run', return_value=payload):
            self.assertEqual(book_title(Path('fallback.pdf')), '见证逆潮')

    def test_book_title_falls_back_when_stdout_is_none(self):
        payload = SimpleNamespace(stdout=None, returncode=0)
        with patch('kr_book_to_audio.extractors.require_command'), patch('kr_book_to_audio.extractors.subprocess.run', return_value=payload):
            self.assertEqual(book_title(Path('fallback-name.pdf')), 'fallback-name')

    def test_diagnose_accepts_utf8_bytes_for_all_poppler_commands(self):
        def fake_run(args, **kwargs):
            self.assertNotIn('text', kwargs)
            if args[0] == 'pdfinfo':
                return SimpleNamespace(stdout='Title: 中文标题\nPages: 3\n'.encode('utf-8'), returncode=0)
            if args[0] == 'pdffonts':
                return SimpleNamespace(stdout=b'name type enc emb sub uni object ID\n---- ---- --- --- --- --- ---------\nFontA Type0 yes yes yes 1 0\n', returncode=0)
            if args[0] == 'pdftotext':
                return SimpleNamespace(stdout=('这是可读取的中文正文。' * 4).encode('utf-8'), returncode=0)
            raise AssertionError(args)
        with tempfile.TemporaryDirectory() as td, patch('kr_book_to_audio.extractors.require_command'), patch('kr_book_to_audio.extractors.subprocess.run', side_effect=fake_run):
            report = diagnose(Path(td) / 'book.pdf')
            self.assertTrue(report['extractable'])
            self.assertGreater(report['sample_cjk_chars'], 20)

    def test_extract_pdf_handles_none_stdout_without_crashing(self):
        payload = SimpleNamespace(stdout=None, returncode=0)
        with patch('kr_book_to_audio.extractors.require_command'), patch('kr_book_to_audio.extractors.subprocess.run', return_value=payload):
            self.assertEqual(extract(Path('fallback.pdf')), '')


if __name__ == '__main__':
    unittest.main()
