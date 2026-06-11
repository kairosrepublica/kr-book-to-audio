from __future__ import annotations
from pathlib import Path
from urllib.parse import unquote
import html
import locale
import os
import re
import shutil
import struct
import zipfile
from xml.etree import ElementTree as ET
from .subprocess_utils import run_hidden_cli
from .utils import require_command, sanitize_filename

_SENTENCE_END = set('。！？!?')

class UnsupportedFormat(RuntimeError):
    pass


def _strip_html(raw: str) -> str:
    raw = re.sub(r'(?is)<(script|style).*?</\1>', '', raw)
    raw = re.sub(r'(?is)<br\s*/?>', '\n', raw)
    raw = re.sub(r'(?is)</(p|div|h[1-6]|li)>', '\n', raw)
    return html.unescape(re.sub(r'(?s)<[^>]+>', '', raw))


def extract_txt(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        try:
            xml = z.read('word/document.xml')
        except KeyError as exc:
            raise UnsupportedFormat('DOCX is missing word/document.xml') from exc
    root = ET.fromstring(xml)
    namespace = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paragraphs = []
    for paragraph in root.findall('.//w:p', namespace):
        text = ''.join(node.text or '' for node in paragraph.findall('.//w:t', namespace)).strip()
        if text:
            paragraphs.append(text)
    return '\n\n'.join(paragraphs)


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


def extract_epub(path: Path) -> str:
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


def extract_mobi(path: Path) -> str:
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

def extract(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {'.txt', '.md'}:
        return extract_txt(path)
    if ext == '.docx':
        return extract_docx(path)
    if ext == '.epub':
        return extract_epub(path)
    if ext in {'.mobi', '.azw', '.prc'}:
        return extract_mobi(path)
    if ext == '.azw3':
        raise UnsupportedFormat('AZW3 / Kindle Format 8 is not yet supported. Convert it to EPUB or MOBI first.')
    if ext == '.pdf':
        pdftotext = _pdf_tool('pdftotext')
        result = run_hidden_cli([pdftotext, '-layout', str(path), '-'], capture_output=True, check=True)
        return _decode_stdout(result.stdout)
    raise UnsupportedFormat(f'Unsupported input format: {ext or "<none>"}')


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
