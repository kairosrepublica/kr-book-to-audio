import tempfile
import unittest
import zipfile
from pathlib import Path
from kr_book_to_audio.extractors import UnsupportedFormat, diagnose, extract_docx

class ExtractorTests(unittest.TestCase):
    def test_docx_extracts_paragraph_text(self):
        xml = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body><w:p><w:r><w:t>第一段</w:t></w:r></w:p><w:p><w:r><w:t>Second</w:t></w:r></w:p></w:body></w:document>"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'book.docx'
            with zipfile.ZipFile(path, 'w') as z: z.writestr('word/document.xml', xml)
            self.assertEqual(extract_docx(path), '第一段\n\nSecond')
    def test_azw3_is_explicitly_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'book.azw3'; path.write_bytes(b'x')
            report = diagnose(path)
            self.assertFalse(report['extractable'])
            self.assertIn('intentionally rejected', report['reason'])

if __name__ == '__main__': unittest.main()
