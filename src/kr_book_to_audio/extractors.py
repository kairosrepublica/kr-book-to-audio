from __future__ import annotations
from pathlib import Path
from urllib.parse import unquote
import html
import os
import re
import struct
import subprocess
import zipfile
from xml.etree import ElementTree as ET
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


def diagnose(path: Path) -> dict:
    ext = path.suffix.lower()
    if ext in {'.txt', '.md', '.docx', '.epub', '.mobi', '.azw', '.prc'}:
        return {'format': ext.lstrip('.'), 'extractable': True, 'needs_ocr': False}
    if ext == '.azw3':
        return {'format': 'azw3', 'extractable': False, 'needs_ocr': False,
                'reason': 'AZW3 / Kindle Format 8 is intentionally rejected until a verified parser fixture exists.'}
    if ext != '.pdf':
        raise UnsupportedFormat(f'Unsupported input format: {ext or "<none>"}')
    require_command('pdfinfo', 'install Poppler')
    require_command('pdffonts', 'install Poppler')
    info = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, check=False).stdout
    fonts = subprocess.run(['pdffonts', str(path)], capture_output=True, text=True, check=False).stdout
    font_rows = [line for line in fonts.splitlines()[2:] if line.strip()]
    pages = re.search(r'Pages:\s+(\d+)', info)
    has_text = bool(font_rows)
    return {'format': 'pdf', 'extractable': has_text, 'needs_ocr': not has_text,
            'pages': int(pages.group(1)) if pages else None}


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
        require_command('pdftotext', 'install Poppler')
        result = subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True, check=True)
        return result.stdout.decode('utf-8', 'replace')
    raise UnsupportedFormat(f'Unsupported input format: {ext or "<none>"}')


def book_title(path: Path) -> str:
    title = None
    if path.suffix.lower() == '.epub':
        title = _epub_title(path)
    elif path.suffix.lower() == '.pdf':
        try:
            require_command('pdfinfo')
            output = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, check=False).stdout
            match = re.search(r'^Title:\s*(.+)$', output, flags=re.MULTILINE)
            if match:
                title = match.group(1).strip()
        except RuntimeError:
            pass
    return sanitize_filename(title or path.stem)
