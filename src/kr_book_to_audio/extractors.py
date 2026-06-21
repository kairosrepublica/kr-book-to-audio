from __future__ import annotations
from pathlib import Path
from urllib.parse import unquote
import html
import tempfile
from html.parser import HTMLParser
import locale
import os
import re
import shutil
import struct
import zipfile
from xml.etree import ElementTree as ET
from .subprocess_utils import run_hidden_cli
from .document_blocks import DocumentBlock, blocks_to_raw_text, normalize_blocks
from .utils import require_command, sanitize_filename

_SENTENCE_END = set('。！？!?')

class UnsupportedFormat(RuntimeError):
    pass


HTML_BLOCK_TAGS = (
    'address', 'article', 'aside', 'blockquote', 'caption', 'center', 'dd', 'div', 'dt',
    'figcaption', 'figure', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'ol', 'p',
    'pre', 'section', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'ul',
)
HTML_BLOCK_RE = re.compile(r'(?is)</?(?:' + '|'.join(HTML_BLOCK_TAGS) + r')(?:\s+[^>]*)?/?>')



def _collapse_spaces(text: str) -> str:
    return re.sub(r'[ \t\r\n]+', ' ', html.unescape(text).replace('\xa0', ' ')).strip()


class _BlockHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[DocumentBlock] = []
        self._tag: str | None = None
        self._level: int | None = None
        self._parts: list[str] = []

    @staticmethod
    def _kind(tag: str) -> tuple[str, int | None]:
        if tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
            return 'heading', int(tag[1])
        if tag == 'li':
            return 'list_item', None
        if tag in {'blockquote'}:
            return 'quote', None
        if tag in {'figcaption', 'caption'}:
            return 'caption', None
        return 'paragraph', None

    def _flush(self) -> None:
        if not self._tag:
            self._parts.clear()
            return
        text = _collapse_spaces(''.join(self._parts))
        if text:
            kind, default_level = self._kind(self._tag)
            self.blocks.append(DocumentBlock(kind, text, level=self._level or default_level, confidence=0.95, source='epub_html'))
        self._tag = None
        self._level = None
        self._parts = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == 'br':
            self._parts.append('\n')
            return
        if tag in HTML_BLOCK_TAGS:
            self._flush()
            self._tag = tag
            if tag.startswith('h') and len(tag) == 2 and tag[1].isdigit():
                self._level = int(tag[1])

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._tag and tag == self._tag:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._tag:
            self._parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def _html_to_blocks(raw: str, *, source: str = 'epub_html') -> list[DocumentBlock]:
    raw = re.sub(r'(?is)<(script|style).*?</\1>', '', raw)
    parser = _BlockHTMLParser()
    parser.feed(raw)
    parser.close()
    if parser.blocks:
        if source != 'epub_html':
            return [DocumentBlock(b.type, b.text, page=b.page, level=b.level, confidence=b.confidence, source=source) for b in parser.blocks]
        return normalize_blocks(parser.blocks)
    # Conservative fallback for malformed HTML: preserve block boundaries via the legacy stripper.
    return [DocumentBlock('paragraph', part, confidence=0.55, source=source) for part in _strip_html(raw).split('\n\n') if part.strip()]


def _strip_html(raw: str) -> str:
    """Convert HTML/XHTML to source text while preserving block boundaries.

    The earlier 3.2 extractor converted closing ``<p>``/``<h*>``/``<li>`` tags
    to a single newline. The later layout cleaner interpreted consecutive
    non-empty lines as one physical block, so entire EPUB chapters collapsed
    into a handful of giant paragraphs. Native EPUB block tags are already
    semantic paragraph/heading boundaries, so preserve them as blank-line
    separated text before prepare-text reflow sees the content.
    """
    raw = re.sub(r'(?is)<(script|style).*?</\1>', '', raw)
    raw = re.sub(r'(?is)<br\s*/?>', '\n', raw)
    raw = HTML_BLOCK_RE.sub('\n\n', raw)
    text = html.unescape(re.sub(r'(?s)<[^>]+>', '', raw)).replace('\xa0', ' ')
    cleaned_lines: list[str] = []
    blank = True
    for line in text.splitlines():
        value = re.sub(r'[ \t]+', ' ', line).strip()
        if not value:
            if not blank:
                cleaned_lines.append('')
            blank = True
            continue
        cleaned_lines.append(value)
        blank = False
    while cleaned_lines and cleaned_lines[-1] == '':
        cleaned_lines.pop()
    return '\n'.join(cleaned_lines)


def extract_txt(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def extract_docx(path: Path) -> str:
    return blocks_to_raw_text(extract_docx_blocks(path))




def extract_txt_blocks(path: Path) -> list[DocumentBlock]:
    text = extract_txt(path)
    blocks: list[DocumentBlock] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append(DocumentBlock('paragraph', '\n'.join(current), confidence=0.70, source='plain_text'))
            current = []

    for line in text.splitlines():
        if line.strip():
            current.append(line.strip())
        else:
            flush()
    flush()
    return normalize_blocks(blocks)


def extract_docx_blocks(path: Path) -> list[DocumentBlock]:
    with zipfile.ZipFile(path) as z:
        try:
            xml = z.read('word/document.xml')
        except KeyError as exc:
            raise UnsupportedFormat('DOCX is missing word/document.xml') from exc
    root = ET.fromstring(xml)
    namespace = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    blocks: list[DocumentBlock] = []
    for paragraph in root.findall('.//w:p', namespace):
        text = ''.join(node.text or '' for node in paragraph.findall('.//w:t', namespace)).strip()
        if not text:
            continue
        style = ''
        pstyle = paragraph.find('.//w:pStyle', namespace)
        if pstyle is not None:
            style = str(pstyle.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')).lower()
        kind = 'heading' if 'heading' in style or style.startswith('title') else 'paragraph'
        level = None
        m = re.search(r'heading\s*([1-6])', style)
        if m:
            level = int(m.group(1))
        blocks.append(DocumentBlock(kind, text, level=level, confidence=0.90, source='docx'))
    return normalize_blocks(blocks)

def _epub_opf(z: zipfile.ZipFile) -> tuple[str, str]:
    names = z.namelist()
    try:
        container = ET.fromstring(z.read('META-INF/container.xml'))
        rootfile = next(node for node in container.iter() if node.tag.endswith('rootfile'))
        opf = rootfile.attrib['full-path']
    except Exception:
        try:
            opf = next(name for name in names if name.lower().endswith('.opf'))
        except StopIteration as exc:
            raise UnsupportedFormat('EPUB has no OPF package document') from exc
    return opf, str(Path(opf).parent).replace('\\', '/')


def _epub_title(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as z:
            opf, _ = _epub_opf(z)
            root = ET.fromstring(z.read(opf))
            for node in root.iter():
                if node.tag.endswith('title') and (node.text or '').strip():
                    return (node.text or '').strip()
    except Exception:
        return None
    return None


def extract_epub_blocks(path: Path) -> list[DocumentBlock]:
    with zipfile.ZipFile(path) as z:
        opf, base = _epub_opf(z)
        package = ET.fromstring(z.read(opf))
        manifest: dict[str, str] = {}
        spine: list[str] = []
        for node in package.iter():
            if node.tag.endswith('item') and node.attrib.get('id') and node.attrib.get('href'):
                media_type = str(node.attrib.get('media-type') or '')
                href = unquote(node.attrib['href'])
                if 'html' in media_type or href.lower().endswith(('.html', '.xhtml', '.htm')):
                    manifest[node.attrib['id']] = href
            elif node.tag.endswith('itemref') and node.attrib.get('idref'):
                spine.append(node.attrib['idref'])
        blocks: list[DocumentBlock] = []
        for item_id in spine:
            href = manifest.get(item_id)
            if not href:
                continue
            member = f'{base}/{href}'.lstrip('/') if base and base != '.' else href
            try:
                payload = z.read(member).decode('utf-8', 'replace')
            except KeyError:
                continue
            item_blocks = _html_to_blocks(payload, source='epub_html')
            body = [block.text for block in item_blocks if block.text.strip()]
            if len(body) >= 12:
                sentence_blocks = sum(1 for text in body if text.rstrip()[-1:] in _SENTENCE_END or re.search(r'[.!?]["”\')]?$', text.rstrip()))
                if sentence_blocks / len(body) < 0.05 and sum(len(x) for x in body) < 1200:
                    continue
            blocks.extend(item_blocks)
        return normalize_blocks(blocks)


def extract_epub(path: Path) -> str:
    blocks = extract_epub_blocks(path)
    if blocks:
        return blocks_to_raw_text(blocks)
    with zipfile.ZipFile(path) as z:
        opf, base = _epub_opf(z)
        package = ET.fromstring(z.read(opf))
        manifest: dict[str, str] = {}
        spine: list[str] = []
        for node in package.iter():
            if node.tag.endswith('item') and node.attrib.get('id') and node.attrib.get('href'):
                manifest[node.attrib['id']] = unquote(node.attrib['href'])
            elif node.tag.endswith('itemref') and node.attrib.get('idref'):
                spine.append(node.attrib['idref'])
        out: list[str] = []
        for item_id in spine:
            href = manifest.get(item_id)
            if not href:
                continue
            member = f'{base}/{href}'.lstrip('/') if base and base != '.' else href
            try:
                lines = _strip_html(z.read(member).decode('utf-8', 'replace')).splitlines()
            except KeyError:
                continue
            body = [line for line in lines if line.strip()]
            if len(body) >= 8:
                sentence_lines = sum(1 for line in body if line.rstrip()[-1:] in _SENTENCE_END)
                if sentence_lines / len(body) < 0.12:
                    continue
            out.extend(lines)
            out.append('')
    return '\n'.join(out)


def _palmdoc_decompress(data: bytes) -> bytes:
    out = bytearray()
    index = 0
    while index < len(data):
        value = data[index]
        index += 1
        if value == 0:
            out.append(0)
        elif value <= 8:
            out.extend(data[index:index + value])
            index += value
        elif value < 0x80:
            out.append(value)
        elif value < 0xC0:
            if index >= len(data):
                break
            token = (value << 8) | data[index]
            index += 1
            distance = (token >> 3) & 0x7FF
            length = (token & 7) + 3
            if distance == 0 or distance > len(out):
                raise UnsupportedFormat('Invalid PalmDOC back-reference')
            for _ in range(length):
                out.append(out[-distance])
        else:
            out.extend(b' ' + bytes([value ^ 0x80]))
    return bytes(out)


def _mobi_trailing_size(payload: bytes, flags: int) -> int:
    def one(data: bytes) -> int:
        bit_pos = result = 0
        cursor = len(data)
        while cursor:
            cursor -= 1
            value = data[cursor]
            result |= (value & 0x7F) << bit_pos
            bit_pos += 7
            if value & 0x80 or bit_pos >= 28:
                return result
        return result
    total = 0
    shifted = flags >> 1
    while shifted:
        if shifted & 1:
            total += one(payload[:len(payload) - total])
        shifted >>= 1
    if flags & 1 and len(payload) > total:
        total += (payload[len(payload) - total - 1] & 0x03) + 1
    return total


def _extract_mobi_palmdoc(path: Path) -> str:
    data = path.read_bytes()
    if len(data) < 100:
        raise UnsupportedFormat('MOBI/PalmDOC file is too short')
    record_count = struct.unpack_from('>H', data, 76)[0]
    offsets = [struct.unpack_from('>I', data, 78 + i * 8)[0] for i in range(record_count)] + [len(data)]
    record = lambda i: data[offsets[i]:offsets[i + 1]]
    header = record(0)
    compression, _, text_length, text_records, _, _ = struct.unpack_from('>HHIHHH', header, 0)
    mobi_length = struct.unpack_from('>I', header, 20)[0] if len(header) >= 32 else 0
    encoding = struct.unpack_from('>I', header, 28)[0] if len(header) >= 32 else 1252
    flags = struct.unpack_from('>H', header, 0xF2)[0] if mobi_length >= 0xF4 and len(header) >= 0xF4 else 0
    raw = bytearray()
    for index in range(1, min(text_records + 1, record_count)):
        payload = record(index)
        trailing = _mobi_trailing_size(payload, flags)
        payload = payload[:len(payload) - trailing] if trailing else payload
        raw.extend(_palmdoc_decompress(payload) if compression == 2 else payload)
    codec = 'utf-8' if encoding == 65001 else 'cp1252'
    return _strip_html(bytes(raw[:text_length]).decode(codec, 'replace'))




def _calibre_ebook_convert() -> str | None:
    for name in ('ebook-convert', 'ebook-convert.exe'):
        found = shutil.which(name)
        if found:
            return found
    return None


def extract_mobi(path: Path) -> str:
    converter = _calibre_ebook_convert()
    if converter:
        with tempfile.TemporaryDirectory(prefix='kr_b2a_mobi_') as td:
            out = Path(td) / 'converted.epub'
            proc = run_hidden_cli([converter, str(path), str(out)], capture_output=True, check=False)
            if proc.returncode == 0 and out.is_file():
                return extract_epub(out)
    try:
        return _extract_mobi_palmdoc(path)
    except UnsupportedFormat as exc:
        raise UnsupportedFormat(
            'MOBI/AZW extraction failed with the built-in legacy PalmDOC parser. '
            'Install Calibre so KR Book To Audio can convert MOBI/AZW to EPUB first, '
            'or provide an EPUB/PDF/TXT source. Original parser error: ' + str(exc)
        ) from exc


def extract_mobi_blocks(path: Path) -> list[DocumentBlock]:
    converter = _calibre_ebook_convert()
    if converter:
        with tempfile.TemporaryDirectory(prefix='kr_b2a_mobi_') as td:
            out = Path(td) / 'converted.epub'
            proc = run_hidden_cli([converter, str(path), str(out)], capture_output=True, check=False)
            if proc.returncode == 0 and out.is_file():
                return extract_epub_blocks(out)
    return [DocumentBlock('paragraph', extract_mobi(path), confidence=0.50, source='mobi_legacy')]

def _pdf_sample_pages(page_count: int | None) -> list[int]:
    if not page_count or page_count < 1:
        return [1]
    return sorted({1, max(1, (page_count + 1) // 2), page_count})


def _decode_stdout(value: object) -> str:
    """Decode external-tool output without trusting the Windows console code page.

    Poppler commonly emits UTF-8 bytes even when Python would otherwise choose a
    legacy Windows text codec for ``text=True``. Reading bytes first avoids reader
    thread crashes and lets us fall back conservatively.
    """
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if not isinstance(value, (bytes, bytearray)):
        return str(value)
    raw = bytes(value)
    preferred = locale.getpreferredencoding(False) or 'utf-8'
    candidates = ['utf-8-sig', preferred, 'gb18030', 'cp1252', 'latin-1']
    seen: set[str] = set()
    for encoding in candidates:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode('utf-8', 'replace')


def _pdf_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return name
    try:
        from .local_ocr import local_ocr_foundation
        candidate = getattr(local_ocr_foundation(), name)
        if Path(candidate).is_file():
            return str(candidate)
    except Exception:
        pass
    return require_command(name, 'install Poppler or run Install / repair local OCR foundation')




def _strip_pdf_noise_lines(pages: list[list[str]]) -> list[list[str]]:
    first_counts: dict[str, int] = {}
    last_counts: dict[str, int] = {}
    for lines in pages:
        meaningful = [line.strip() for line in lines if line.strip()]
        if not meaningful:
            continue
        first_counts[meaningful[0]] = first_counts.get(meaningful[0], 0) + 1
        last_counts[meaningful[-1]] = last_counts.get(meaningful[-1], 0) + 1
    page_count = max(len(pages), 1)
    repeated = {
        line for line, count in {**first_counts, **last_counts}.items()
        if count >= 3 and (count / page_count >= 0.25 or len(line) <= 80)
    }
    cleaned_pages: list[list[str]] = []
    footer_pattern = re.compile(r'(?i)(https?://|www\.|页码\s*[:：]?\s*\d+\s*/\s*\d+|^\s*(?:页|码|页\s*[:：]?|[:：]+)\s*$|^\s*\d+\s*/\s*\d+\s*$)')
    for lines in pages:
        cleaned: list[str] = []
        for line in lines:
            value = re.sub(r'[ \t]+', ' ', line).strip()
            if not value:
                cleaned.append('')
                continue
            if value in repeated or footer_pattern.search(value):
                continue
            cleaned.append(value)
        cleaned_pages.append(cleaned)
    return cleaned_pages


def extract_pdf_blocks(path: Path) -> list[DocumentBlock]:
    pdftotext = _pdf_tool('pdftotext')
    result = run_hidden_cli([pdftotext, '-layout', str(path), '-'], capture_output=True, check=True)
    raw = _decode_stdout(result.stdout)
    pages = [page.splitlines() for page in raw.split('\f')]
    pages = _strip_pdf_noise_lines(pages)
    blocks: list[DocumentBlock] = []
    for page_index, lines in enumerate(pages, 1):
        current: list[str] = []

        def flush() -> None:
            nonlocal current
            if current:
                text = '\n'.join(line for line in current if line.strip()).strip()
                if text:
                    blocks.append(DocumentBlock('paragraph', text, page=page_index, confidence=0.72, source='pdf_native'))
                current = []

        for line in lines:
            if line.strip():
                current.append(line.strip())
            else:
                flush()
        flush()
    return normalize_blocks(blocks)

def diagnose(path: Path) -> dict:
    ext = path.suffix.lower()
    if ext in {'.txt', '.md', '.docx', '.epub', '.mobi', '.azw', '.prc'}:
        return {'format': ext.lstrip('.'), 'extractable': True, 'needs_ocr': False}
    if ext == '.azw3':
        return {'format': 'azw3', 'extractable': False, 'needs_ocr': False,
                'reason': 'AZW3 / Kindle Format 8 is intentionally rejected until a verified parser fixture exists.'}
    if ext != '.pdf':
        raise UnsupportedFormat(f'Unsupported input format: {ext or "<none>"}')
    pdfinfo = _pdf_tool('pdfinfo')
    pdffonts = _pdf_tool('pdffonts')
    pdftotext = _pdf_tool('pdftotext')
    info_result = run_hidden_cli([pdfinfo, str(path)], capture_output=True, check=False)
    fonts_result = run_hidden_cli([pdffonts, str(path)], capture_output=True, check=False)
    info = _decode_stdout(info_result.stdout)
    fonts = _decode_stdout(fonts_result.stdout)
    font_rows = [line for line in fonts.splitlines()[2:] if line.strip()]
    pages_match = re.search(r'Pages:\s+(\d+)', info)
    page_count = int(pages_match.group(1)) if pages_match else None
    sample_texts = []
    sample_pages = _pdf_sample_pages(page_count)
    for page in sample_pages:
        result = run_hidden_cli([pdftotext, '-f', str(page), '-l', str(page), '-layout', str(path), '-'], capture_output=True, check=False)
        if result.returncode == 0:
            sample_texts.append(_decode_stdout(result.stdout))
    sample = '\n'.join(sample_texts)
    nonspace = [char for char in sample if not char.isspace()]
    readable = sum(1 for char in nonspace if char.isalnum() or '\u3400' <= char <= '\u9fff')
    cjk = sum(1 for char in nonspace if '\u3400' <= char <= '\u9fff')
    usable_sample = readable >= 20
    extractable = bool(font_rows) and usable_sample
    reason = None
    if not font_rows:
        reason = 'PDF has no detected font rows. It appears image-only and requires OCR first.'
    elif not usable_sample:
        reason = 'PDF exposes fonts but sampled pages did not yield usable prose. Re-OCR or choose a better source.'
    return {
        'format': 'pdf',
        'extractable': extractable,
        'needs_ocr': not extractable,
        'pages': page_count,
        'sample_pages': sample_pages,
        'sample_nonspace_chars': len(nonspace),
        'sample_readable_chars': readable,
        'sample_cjk_chars': cjk,
        'reason': reason,
    }

def extract_blocks(path: Path) -> list[DocumentBlock]:
    ext = path.suffix.lower()
    if ext in {'.txt', '.md'}:
        return extract_txt_blocks(path)
    if ext == '.docx':
        return extract_docx_blocks(path)
    if ext == '.epub':
        return extract_epub_blocks(path)
    if ext in {'.mobi', '.azw', '.prc'}:
        return extract_mobi_blocks(path)
    if ext == '.azw3':
        raise UnsupportedFormat('AZW3 / Kindle Format 8 is not yet supported. Convert it to EPUB first.')
    if ext == '.pdf':
        return extract_pdf_blocks(path)
    raise UnsupportedFormat(f'Unsupported input format: {ext or "<none>"}')


def extract(path: Path) -> str:
    return blocks_to_raw_text(extract_blocks(path))


def book_title(path: Path) -> str:
    title = None
    if path.suffix.lower() == '.epub':
        title = _epub_title(path)
    elif path.suffix.lower() == '.pdf':
        try:
            pdfinfo = _pdf_tool('pdfinfo')
            output = _decode_stdout(run_hidden_cli([pdfinfo, str(path)], capture_output=True, check=False).stdout)
            match = re.search(r'^Title:\s*(.+)$', output or '', flags=re.MULTILINE)
            if match:
                title = match.group(1).strip()
        except RuntimeError:
            pass
    return sanitize_filename(title or path.stem)
