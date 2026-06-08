from __future__ import annotations
from collections import Counter
from pathlib import Path
import json
import re

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SENT_END = set('。！？…”》）)】"!?」』.')
_DATE_TOKEN = r"\d{4}\s*(?:[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}|年\s*\d{1,2}\s*月\s*\d{1,2}\s*日?)"
_TIME_TOKEN = r"[ T]\s*[0-2]?\d\s*:\s*[0-5]\d(?:\s*:\s*[0-5]\d)?"
BRACKETED_METADATA_DATETIME = re.compile(rf"[（(\[【]\s*{_DATE_TOKEN}(?:{_TIME_TOKEN})?\s*[）)\]】]")
BARE_METADATA_DATETIME = re.compile(rf"(?<!\d){_DATE_TOKEN}{_TIME_TOKEN}(?!\d)")
CJK_PUNCT = '，。、！？；：“”‘’（）《》【】…—·「」『』'
ADJ = '[\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff' + re.escape(CJK_PUNCT) + ']'
SP_AFTER = re.compile('(?<=' + ADJ + r')[ \t]+')
SP_BEFORE = re.compile(r'[ \t]+(?=' + ADJ + ')')
AD_RE = re.compile(r'(?i)(https?://|www\.|微信|公众号|盗版|请支持正版|本书由.+整理|扫描版|z-library)')


def n_cjk(text: str) -> int:
    return len(CJK.findall(text))


def text_units(text: str) -> int:
    """Measure chunk pressure: CJK characters for Chinese-heavy text, compact characters otherwise."""
    compact = re.sub(r'\s', '', text)
    if not compact:
        return 0
    cjk = n_cjk(text)
    return cjk if cjk / len(compact) >= 0.20 else len(compact)


def normalize_cjk(text: str) -> str:
    """Remove PDF glyph-gap whitespace adjacent to Chinese characters or punctuation."""
    return SP_BEFORE.sub('', SP_AFTER.sub('', text))


def strip_metadata_datetime_tags(text: str) -> str:
    """Remove source-style timestamp tags without deleting ordinary prose dates or times."""
    return BARE_METADATA_DATETIME.sub('', BRACKETED_METADATA_DATETIME.sub('', text))


def detect_processing_profile(text: str) -> str:
    compact = re.sub(r'\s', '', text)
    if not compact:
        return 'general-prose'
    cjk = n_cjk(text)
    latin = sum(1 for char in compact if char.isascii() and char.isalpha())
    if cjk >= 20 and latin >= 20 and min(cjk, latin) / max(cjk, latin) >= 0.12:
        return 'mixed'
    if cjk >= max(10, latin * 2):
        return 'chinese'
    if latin >= max(10, cjk * 2):
        return 'english'
    return 'general-prose'


def analyze_cleanup(text: str, *, min_repeats: int = 3, max_len: int = 50) -> dict:
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    counts = Counter(paragraphs)
    repeated = []
    ambiguous = []
    for paragraph in paragraphs:
        if AD_RE.search(paragraph):
            repeated.append({'reason': 'advertisement-or-url', 'text': paragraph, 'confidence': 'high'})
        elif len(paragraph) <= max_len and counts[paragraph] >= min_repeats:
            target = {'reason': 'repeated-short-paragraph', 'text': paragraph, 'count': counts[paragraph]}
            if counts[paragraph] >= max(5, min_repeats + 2) or len(paragraph) <= 24:
                repeated.append({**target, 'confidence': 'high'})
            else:
                ambiguous.append({**target, 'confidence': 'review'})
    datetime_matches = []
    for match in BRACKETED_METADATA_DATETIME.finditer(text):
        datetime_matches.append({'text': match.group(0), 'confidence': 'high', 'reason': 'bracketed-metadata-date-time'})
    for match in BARE_METADATA_DATETIME.finditer(text):
        datetime_matches.append({'text': match.group(0), 'confidence': 'high', 'reason': 'bare-metadata-date-time'})
    def status(high, review=None):
        if review:
            return 'review-required'
        return 'recommended' if high else 'not-needed'
    return {
        'repeated_headers_and_junk': {'status': status(repeated, ambiguous), 'high_confidence': repeated, 'review': ambiguous, 'count': len(repeated)},
        'metadata_datetime_tags': {'status': status(datetime_matches), 'high_confidence': datetime_matches, 'review': [], 'count': len(datetime_matches)},
    }


def apply_cleanup(text: str, kind: str, *, min_repeats: int = 3) -> tuple[str, dict]:
    if kind == 'repeated-headers-and-junk':
        analysis = analyze_cleanup(text, min_repeats=min_repeats)
        approved = {(item['reason'], item['text']) for item in analysis['repeated_headers_and_junk']['high_confidence']}
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        kept: list[str] = []
        removed: list[dict] = []
        counts = Counter(paragraphs)
        for paragraph in paragraphs:
            reason = 'advertisement-or-url' if AD_RE.search(paragraph) else 'repeated-short-paragraph'
            if (reason, paragraph) in approved:
                removed.append({'reason': reason, 'text': paragraph})
            else:
                kept.append(paragraph)
        return '\n\n'.join(kept), {'removed': removed, 'kept_paragraphs': len(kept), 'review_preserved': analysis['repeated_headers_and_junk']['review']}
    if kind == 'metadata-date-time-tags':
        before = list(BRACKETED_METADATA_DATETIME.finditer(text)) + list(BARE_METADATA_DATETIME.finditer(text))
        cleaned = strip_metadata_datetime_tags(text)
        return cleaned, {'removed_count': len(before), 'kind': kind}
    raise ValueError(f'Unknown cleanup kind: {kind}')


def clean_text(raw: str, *, strip_datetime_tags: bool = False, cjk_ratio: float = 0.55, processing_profile: str = 'auto') -> tuple[str, dict]:
    """Conservatively reflow extracted prose while removing deterministic page noise."""
    pages = raw.split('\f')
    leaders = Counter()
    for page in pages:
        first = next((line.strip() for line in page.splitlines() if line.strip()), None)
        if first:
            leaders[first] += 1
    running = {line for line, count in leaders.items() if count >= 3 and len(line) < 40}

    lines: list[str] = []
    for page in pages:
        first_seen = False
        for line in page.splitlines():
            value = line.strip()
            if not value:
                lines.append('')
                continue
            if not first_seen:
                first_seen = True
                if value in running or re.fullmatch(r'\d{1,5}', value):
                    continue
            if re.fullmatch(r'\d{1,5}', value):
                continue
            if strip_datetime_tags:
                value = strip_metadata_datetime_tags(value)
            lines.append(value)

    paragraphs: list[str] = []
    buffer = ''
    for line in lines:
        value = line.strip()
        if not value:
            if buffer and buffer[-1] in SENT_END:
                paragraphs.append(buffer)
                buffer = ''
            continue
        if n_cjk(value) < 2 and len(value) < 12:
            continue
        buffer += value
        if buffer and buffer[-1] in SENT_END:
            paragraphs.append(buffer)
            buffer = ''
    if buffer:
        paragraphs.append(buffer)

    raw_compact = re.sub(r'\s', '', raw)
    detected_profile = detect_processing_profile(raw)
    selected_profile = detected_profile if processing_profile == 'auto' else processing_profile
    chinese_mode = selected_profile in {'chinese', 'mixed'}
    kept: list[str] = []
    for paragraph in paragraphs:
        paragraph = normalize_cjk(paragraph)
        compact = re.sub(r'\s', '', paragraph)
        if len(compact) < 4:
            continue
        if chinese_mode and n_cjk(paragraph) / max(len(compact), 1) < cjk_ratio:
            continue
        if kept and kept[-1] == paragraph:
            continue
        kept.append(paragraph)

    body = '\n\n'.join(kept)
    stats = {
        'language_mode': selected_profile,
        'detected_profile': detected_profile,
        'requested_profile': processing_profile,
        'cjk_chars': n_cjk(body),
        'paragraphs': len(kept),
        'residual_exact_duplicates': sum(c - 1 for c in Counter(kept).values() if c > 1),
        'running_headers_removed': sorted(running),
        'residual_intra_cjk_spaces': len(re.findall(r'[\u3400-\u9fff] +[\u3400-\u9fff]', body)),
        'metadata_datetime_cleanup': bool(strip_datetime_tags),
    }
    return body, stats


def strip_repeated_junk(text: str, *, min_repeats: int = 3, max_len: int = 50) -> tuple[str, dict]:
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    counts = Counter(paragraphs)
    kept: list[str] = []
    removed: list[dict] = []
    for paragraph in paragraphs:
        reason = None
        if AD_RE.search(paragraph):
            reason = 'advertisement-or-url'
        elif len(paragraph) <= max_len and counts[paragraph] >= min_repeats:
            reason = 'repeated-short-paragraph'
        if reason:
            removed.append({'reason': reason, 'text': paragraph})
        else:
            kept.append(paragraph)
    return '\n\n'.join(kept), {'removed': removed, 'kept_paragraphs': len(kept)}


def load_dictionary(path: Path | None) -> list[dict]:
    if path is None or not Path(path).exists():
        return []
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    entries = payload.get('replacements', payload) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError('Pronunciation dictionary must be a list or contain a replacements list.')
    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Each pronunciation replacement must be an object.')
        find = str(entry.get('find', ''))
        replace = str(entry.get('replace', ''))
        enabled = bool(entry.get('enabled', True))
        if enabled and find:
            normalized.append({'find': find, 'replace': replace, 'enabled': True})
    normalized.sort(key=lambda item: (-len(item['find']), item['find']))
    return normalized


def apply_dictionary(text: str, entries: list[dict]) -> tuple[str, list[dict]]:
    rendered = text
    preview = []
    for entry in entries:
        find = entry['find']
        replace = entry['replace']
        count = rendered.count(find)
        if count:
            rendered = rendered.replace(find, replace)
        preview.append({'find': find, 'replace': replace, 'count': count})
    return rendered, preview


def _split_hard(text: str, max_cjk: int) -> list[str]:
    """Fallback splitter for pathological no-punctuation runs."""
    pieces, buffer = [], []
    for char in text:
        buffer.append(char)
        if text_units(''.join(buffer)) >= max_cjk:
            pieces.append(''.join(buffer).strip())
            buffer = []
    if buffer:
        pieces.append(''.join(buffer).strip())
    return [p for p in pieces if p]


def split_oversized_paragraph(paragraph: str, max_cjk: int) -> list[str]:
    if text_units(paragraph) <= max_cjk:
        return [paragraph]
    sentences = re.split(r'(?<=[。！？!?；;])', paragraph)
    pieces: list[str] = []
    current = ''
    for sentence in sentences:
        if not sentence:
            continue
        if text_units(sentence) > max_cjk:
            if current:
                pieces.append(current)
                current = ''
            pieces.extend(_split_hard(sentence, max_cjk))
        elif current and text_units(current) + text_units(sentence) > max_cjk:
            pieces.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        pieces.append(current)
    return [piece for piece in pieces if piece]


def chunk_text(text: str, *, max_cjk: int = 9000) -> list[str]:
    if max_cjk < 100:
        raise ValueError('max_cjk must be >= 100')
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    expanded: list[str] = []
    for paragraph in paragraphs:
        expanded.extend(split_oversized_paragraph(paragraph, max_cjk))
    parts: list[str] = []
    current: list[str] = []
    current_count = 0
    for paragraph in expanded:
        count = text_units(paragraph)
        if current and current_count + count > max_cjk:
            parts.append('\n\n'.join(current))
            current, current_count = [], 0
        current.append(paragraph)
        current_count += count
    if current:
        parts.append('\n\n'.join(current))
    return parts
