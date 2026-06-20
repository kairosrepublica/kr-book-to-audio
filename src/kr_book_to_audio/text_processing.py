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
AD_RE = re.compile(r'(?i)(https?://|www\.|盗版|请支持正版|本书由.+整理|扫描版|z-library)')


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


LAYOUT_MODES = {'standard', 'structure-aware', 'minimal'}
ARTICLE_INTRO_RE = re.compile(r'^(?:以下为|本文最初|本文最早|本文首发|原文|作者按|按语)')
ARTICLE_TITLE_RE = re.compile(r'^(?:\d{4}\s*年\s*\d{1,2}\s*月.*(?:微博|发言|摘要|合集))$')
SECTION_MARKER_RE = re.compile(r'^(?:第\s*[一二三四五六七八九十百千万两0-9]+\s*[，、,.．]\s*[^。！？!?；;]{0,40}|[一二三四五六七八九十]+\s*[、.．]\s*[^。！？!?；;]{0,40})$')
ORDINAL_START_RE = re.compile(r'^第\s*[一二三四五六七八九十百千万两0-9]+\s*[，、,.．]')
ARTICLE_TERMINATOR_RE = re.compile(r'(?:未完待续|全文完|END|待续)[）)】\]]?\s*$')


def _compact_units(text: str) -> int:
    return text_units(text)


def _has_sentence_punctuation(text: str) -> bool:
    return bool(re.search(r'[。！？!?；;]', text))


def _ends_sentence(text: str) -> bool:
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in SENT_END


def _join_extracted_lines(lines: list[str]) -> str:
    """Join physical extraction lines inside one source block.

    CJK-heavy blocks are joined without an inserted space because many PDF/OCR
    and copied Chinese sources contain artificial glyph gaps. Latin-only blocks
    keep a single space so English words do not collide.
    """
    cleaned = [line.strip() for line in lines if line.strip()]
    if not cleaned:
        return ''
    combined = ''.join(cleaned)
    compact = re.sub(r'\s', '', combined)
    cjk = n_cjk(combined)
    if compact and cjk / max(len(compact), 1) < 0.20:
        return ' '.join(cleaned)
    return combined


def _line_blocks(lines: list[str]) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        value = line.strip()
        if not value:
            if current:
                joined = _join_extracted_lines(current).strip()
                if joined:
                    blocks.append(joined)
                current = []
            continue
        current.append(value)
    if current:
        joined = _join_extracted_lines(current).strip()
        if joined:
            blocks.append(joined)
    return blocks


def is_section_heading(text: str) -> bool:
    compact = re.sub(r'\s', '', text.strip())
    if not compact or _compact_units(compact) > 60:
        return False
    return bool(SECTION_MARKER_RE.match(compact))


def is_article_heading(text: str, *, next_text: str = '', previous_text: str = '', index: int = 0) -> bool:
    value = text.strip()
    compact = re.sub(r'\s', '', value)
    if not compact or _compact_units(compact) > 90:
        return False
    if ORDINAL_START_RE.match(compact):
        return False
    if ARTICLE_INTRO_RE.match(next_text.strip()):
        return True
    if ARTICLE_TITLE_RE.match(compact) and not _has_sentence_punctuation(value):
        return True
    if ARTICLE_TERMINATOR_RE.search(previous_text.strip()) and not _has_sentence_punctuation(value):
        return True
    return False


def is_structural_heading(text: str, *, next_text: str = '', previous_text: str = '', index: int = 0) -> bool:
    return is_article_heading(text, next_text=next_text, previous_text=previous_text, index=index) or is_section_heading(text)


def _clean_blocks_standard(blocks: list[str]) -> tuple[list[str], dict]:
    paragraphs: list[str] = []
    buffer = ''
    for block in blocks:
        value = block.strip()
        if not value:
            continue
        if n_cjk(value) < 2 and len(value) < 12:
            continue
        buffer += value
        if buffer and _ends_sentence(buffer):
            paragraphs.append(buffer)
            buffer = ''
    if buffer:
        paragraphs.append(buffer)
    return paragraphs, {'layout_mode': 'standard', 'structural_breaks_preserved': 0, 'artificial_breaks_reflowed': 0}


def _clean_blocks_minimal(blocks: list[str]) -> tuple[list[str], dict]:
    return blocks[:], {'layout_mode': 'minimal', 'structural_breaks_preserved': len(blocks), 'artificial_breaks_reflowed': 0}


def _clean_blocks_structure_aware(blocks: list[str]) -> tuple[list[str], dict]:
    paragraphs: list[str] = []
    buffer = ''
    structural_breaks = 0
    artificial_breaks = 0
    for index, block in enumerate(blocks):
        value = block.strip()
        if not value:
            continue
        if n_cjk(value) < 2 and len(value) < 12:
            continue
        previous_text = blocks[index - 1] if index > 0 else ''
        next_text = blocks[index + 1] if index + 1 < len(blocks) else ''
        structural = is_structural_heading(value, next_text=next_text, previous_text=previous_text, index=index)
        if structural:
            if buffer:
                paragraphs.append(buffer)
                buffer = ''
            paragraphs.append(value)
            structural_breaks += 1
            continue
        if buffer:
            buffer += value
            artificial_breaks += 1
        else:
            buffer = value
        if buffer and _ends_sentence(buffer):
            paragraphs.append(buffer)
            buffer = ''
    if buffer:
        paragraphs.append(buffer)
    return paragraphs, {'layout_mode': 'structure-aware', 'structural_breaks_preserved': structural_breaks, 'artificial_breaks_reflowed': artificial_breaks}


def _select_layout_mode(layout_mode: str | None, preserve_paragraph_breaks: bool) -> str:
    if layout_mode in {None, 'auto'}:
        return 'minimal' if preserve_paragraph_breaks else 'standard'
    if layout_mode not in LAYOUT_MODES:
        raise ValueError(f'Unknown text layout mode: {layout_mode}')
    return layout_mode


def clean_text(
    raw: str,
    *,
    strip_datetime_tags: bool = False,
    cjk_ratio: float = 0.55,
    processing_profile: str = 'auto',
    preserve_paragraph_breaks: bool = False,
    layout_mode: str | None = None,
) -> tuple[str, dict]:
    """Conservatively prepare prose while separating cleaning from layout policy.

    ``standard`` is the legacy aggressive reflow path for noisy PDF/OCR text.
    ``minimal`` preserves explicit source paragraph blocks and is intended for
    Owner-approved, already-clean TXT/MD/DOCX input.
    ``structure-aware`` is the default for plain text-like sources: it preserves
    high-confidence article titles and section headings, but continues to reflow
    incomplete broken paragraphs so messy ebooks are not silently passed through.
    """
    selected_layout_mode = _select_layout_mode(layout_mode, preserve_paragraph_breaks)
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

    blocks = _line_blocks(lines)
    if selected_layout_mode == 'minimal':
        paragraphs, layout_stats = _clean_blocks_minimal(blocks)
    elif selected_layout_mode == 'structure-aware':
        paragraphs, layout_stats = _clean_blocks_structure_aware(blocks)
    else:
        paragraphs, layout_stats = _clean_blocks_standard(blocks)

    detected_profile = detect_processing_profile(raw)
    selected_profile = detected_profile if processing_profile == 'auto' else processing_profile
    chinese_mode = selected_profile in {'chinese', 'mixed'}
    kept: list[str] = []
    for paragraph in paragraphs:
        paragraph = normalize_cjk(paragraph)
        compact = re.sub(r'\s', '', paragraph)
        if len(compact) < 4:
            continue
        if chinese_mode and selected_layout_mode == 'standard' and n_cjk(paragraph) / max(len(compact), 1) < cjk_ratio:
            continue
        if kept and kept[-1] == paragraph:
            continue
        kept.append(paragraph)

    body = '\n\n'.join(kept)
    article_boundaries = detect_article_boundaries(kept)
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
        'preserve_paragraph_breaks': selected_layout_mode == 'minimal',
        'layout_mode': selected_layout_mode,
        'source_blocks': len(blocks),
        'structural_breaks_preserved': layout_stats.get('structural_breaks_preserved', 0),
        'artificial_breaks_reflowed': layout_stats.get('artificial_breaks_reflowed', 0),
        'article_boundaries_detected': len(article_boundaries),
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


DIRECT_LEXICON_SECTIONS = ('acronyms', 'abbreviations', 'units')
LEXICON_METADATA_SECTIONS = (
    'normalization_rules',
    'heteronyms',
    'phrase_pronunciations',
    'place_names',
    'surname_readings',
    'neutral_tone_phrases',
    'fallbacks',
)


def _normalize_replacement_entries(entries: list[dict]) -> list[dict]:
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


def _load_direct_lexicon_replacements(payload: dict) -> list[dict] | None:
    """Return safe direct substitutions from a structured pronunciation lexicon.

    The app's pronunciation dictionary is a literal pre-TTS replacement list.
    Rich lexicon sections such as IPA heteronyms or Chinese pinyin readings are
    metadata, not safe text substitutions for Edge/native TTS, so only entries
    that already contain source -> spoken text are imported here.
    """
    recognized = any(key in payload for key in (*DIRECT_LEXICON_SECTIONS, *LEXICON_METADATA_SECTIONS))
    if not recognized:
        return None

    replacements = []
    for section in DIRECT_LEXICON_SECTIONS:
        items = payload.get(section, [])
        if items is None:
            continue
        if not isinstance(items, list):
            raise ValueError(f'Pronunciation lexicon section {section!r} must be a list.')
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f'Each pronunciation lexicon entry in {section!r} must be an object.')
            find = str(item.get('source', ''))
            replace = str(item.get('spoken', ''))
            enabled = bool(item.get('enabled', True))
            if enabled and find:
                replacements.append({'find': find, 'replace': replace, 'enabled': True})
    return _normalize_replacement_entries(replacements)


def load_dictionary(path: Path | None) -> list[dict]:
    if path is None or not Path(path).exists():
        return []
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(payload, list):
        return _normalize_replacement_entries(payload)
    if isinstance(payload, dict):
        if 'replacements' in payload:
            entries = payload['replacements']
            if not isinstance(entries, list):
                raise ValueError('Pronunciation dictionary replacements must be a list.')
            return _normalize_replacement_entries(entries)
        lexicon_replacements = _load_direct_lexicon_replacements(payload)
        if lexicon_replacements is not None:
            return lexicon_replacements
    raise ValueError(
        'Pronunciation dictionary must be a list, contain a replacements list, '
        'or be a supported pronunciation lexicon with source/spoken direct entries.'
    )


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


def detect_article_boundaries(paragraphs: list[str]) -> list[int]:
    boundaries: list[int] = []
    for index, paragraph in enumerate(paragraphs):
        next_text = paragraphs[index + 1] if index + 1 < len(paragraphs) else ''
        previous_text = paragraphs[index - 1] if index > 0 else ''
        if is_article_heading(paragraph, next_text=next_text, previous_text=previous_text, index=index):
            boundaries.append(index)
    if boundaries and boundaries[0] != 0:
        boundaries.insert(0, 0)
    return sorted(set(boundaries))


def _article_units(paragraphs: list[str]) -> list[str]:
    boundaries = detect_article_boundaries(paragraphs)
    if len(boundaries) < 2:
        return paragraphs[:]
    stops = boundaries[1:] + [len(paragraphs)]
    units: list[str] = []
    for start, stop in zip(boundaries, stops):
        unit = '\n\n'.join(p for p in paragraphs[start:stop] if p.strip()).strip()
        if unit:
            units.append(unit)
    return units


def chunk_text(text: str, *, max_cjk: int = 9000, prefer_article_boundaries: bool = True) -> list[str]:
    if max_cjk < 100:
        raise ValueError('max_cjk must be >= 100')
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if prefer_article_boundaries:
        primary_units = _article_units(paragraphs)
    else:
        primary_units = paragraphs[:]

    expanded: list[str] = []
    for unit in primary_units:
        if text_units(unit) <= max_cjk:
            expanded.append(unit)
            continue
        unit_paragraphs = [p.strip() for p in unit.split('\n\n') if p.strip()]
        if len(unit_paragraphs) > 1:
            for paragraph in unit_paragraphs:
                expanded.extend(split_oversized_paragraph(paragraph, max_cjk))
        else:
            expanded.extend(split_oversized_paragraph(unit, max_cjk))

    parts: list[str] = []
    current: list[str] = []
    current_count = 0
    for unit in expanded:
        count = text_units(unit)
        if current and current_count + count > max_cjk:
            parts.append('\n\n'.join(current))
            current, current_count = [], 0
        current.append(unit)
        current_count += count
    if current:
        parts.append('\n\n'.join(current))
    return parts
