import tempfile
import unittest
import zipfile
from pathlib import Path
from kr_book_to_audio.extractors import UnsupportedFormat, diagnose, extract_docx, extract_epub

class ExtractorTests(unittest.TestCase):
    def test_docx_extracts_paragraph_text(self):
        xml = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body><w:p><w:r><w:t>第一段</w:t></w:r></w:p><w:p><w:r><w:t>Second</w:t></w:r></w:p></w:body></w:document>"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'book.docx'
            with zipfile.ZipFile(path, 'w') as z: z.writestr('word/document.xml', xml)
            self.assertEqual(extract_docx(path), '第一段\n\nSecond')

    def test_epub_extract_preserves_html_block_boundaries(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'book.epub'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('META-INF/container.xml', '''<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''')
                z.writestr('OPS/content.opf', '''<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="c1" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>''')
                z.writestr('OPS/chapter.xhtml', '''<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Chapter One</h1><p>First paragraph.</p><p>Second paragraph.</p><h2>Subheading</h2><p>Third paragraph.</p></body></html>''')
            extracted = extract_epub(path)
            self.assertIn('Chapter One\n\nFirst paragraph.', extracted)
            self.assertIn('First paragraph.\n\nSecond paragraph.', extracted)
            self.assertIn('Subheading\n\nThird paragraph.', extracted)

    def test_azw3_is_explicitly_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'book.azw3'; path.write_bytes(b'x')
            report = diagnose(path)
            self.assertFalse(report['extractable'])
            self.assertIn('intentionally rejected', report['reason'])

if __name__ == '__main__': unittest.main()
