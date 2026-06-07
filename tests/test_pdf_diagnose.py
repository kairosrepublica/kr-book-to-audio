import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from kr_book_to_audio.extractors import diagnose

class PdfDiagnoseTests(unittest.TestCase):
    def _run(self, args, **kwargs):
        command = args[0]
        if command == 'pdfinfo':
            return SimpleNamespace(stdout='Pages:          9\n', returncode=0)
        if command == 'pdffonts':
            return SimpleNamespace(stdout='name type enc emb sub uni object ID\n---- ---- --- --- --- --- ---------\nFontA Type0 yes yes yes 1 0\n', returncode=0)
        if command == 'pdftotext':
            return SimpleNamespace(stdout=('这是可读取的中文正文。' * 4).encode('utf-8'), returncode=0)
        raise AssertionError(args)

    def _empty_run(self, args, **kwargs):
        command = args[0]
        if command == 'pdfinfo':
            return SimpleNamespace(stdout='Pages:          9\n', returncode=0)
        if command == 'pdffonts':
            return SimpleNamespace(stdout='name type enc emb sub uni object ID\n---- ---- --- --- --- --- ---------\nFontA Type0 yes yes yes 1 0\n', returncode=0)
        if command == 'pdftotext':
            return SimpleNamespace(stdout=b'', returncode=0)
        raise AssertionError(args)

    def test_pdf_fonts_and_usable_sample_are_required(self):
        with tempfile.TemporaryDirectory() as td, patch('kr_book_to_audio.extractors.require_command'), patch('kr_book_to_audio.extractors.subprocess.run', side_effect=self._run):
            report = diagnose(Path(td) / 'book.pdf')
            self.assertTrue(report['extractable'])
            self.assertEqual(report['sample_pages'], [1, 5, 9])
            self.assertGreater(report['sample_cjk_chars'], 20)

    def test_pdf_fonts_without_usable_sample_are_rejected(self):
        with tempfile.TemporaryDirectory() as td, patch('kr_book_to_audio.extractors.require_command'), patch('kr_book_to_audio.extractors.subprocess.run', side_effect=self._empty_run):
            report = diagnose(Path(td) / 'book.pdf')
            self.assertFalse(report['extractable'])
            self.assertTrue(report['needs_ocr'])
            self.assertIn('sampled pages', report['reason'])

if __name__ == '__main__': unittest.main()
