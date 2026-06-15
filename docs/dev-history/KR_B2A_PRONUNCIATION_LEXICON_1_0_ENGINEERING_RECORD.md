# KR B2A Pronunciation Lexicon 1.0

## Research, Engineering Decisions, and Production Record

Release: KR B2A Pronunciation Lexicon - Istanbul Release 1.0

Date: 2026-06-15

Repository: https://github.com/kairosrepublica/kr-book-to-audio

Classification: Public engineering history

## 1. Executive summary

This work began with a practical audiobook-production question: whether one
general-purpose pronunciation lexicon could cover the common failure modes of
Chinese-language books and whether English required an equivalent resource.

The research established that a large static word list is useful but
insufficient. Mandarin pronunciation requires phrase and sentence context for
polyphonic characters. English spelling is not a deterministic pronunciation
system and contains heteronyms, stress shifts, names, loanwords, and acronyms.
Dates, numbers, units, symbols, URLs, identifiers, and mixed-language passages
are text-normalization problems rather than ordinary dictionary lookups.

The resulting release therefore uses a layered architecture:

1. text cleanup and language-span detection;
2. project-specific pronunciation overrides;
3. contextual phrase entries;
4. date, number, unit, symbol, and acronym normalization;
5. full external pronunciation dictionaries;
6. language-specific grapheme-to-phoneme fallback;
7. explicit low-confidence reporting and human listening review.

The release artifact is an encrypted ZIP with a separately published SHA-256
receipt. The password is distributed only on request through
kr@kairosrepublica.com.

## 2. Scope and constraints

### In scope

- Simplified Mandarin audiobook preparation with useful traditional-form
  coverage from CC-CEDICT.
- Common Mandarin polyphones, neutral tones, surnames, place names, historical
  readings, religious terms, acronyms, technical terms, and mixed-language
  passages.
- US-English pronunciation lookup, heteronym handling, abbreviations,
  acronyms, specialist terms, and out-of-vocabulary fallback.
- Dates, times, cardinals, ordinals, decimals, fractions, percentages, ratios,
  ranges, versions, identifiers, scientific notation, currencies, and units.
- A machine-readable JSON/JSONL release suitable for adapters, preprocessing,
  SSML generation, or engine-specific lexicon conversion.
- Source attribution, license boundaries, validation evidence, and a public
  release record.

### Out of scope

- Claiming infallible pronunciation for every book.
- Replacing a contextual Mandarin G2P model.
- Replacing an English G2P model for unknown words.
- Solving prosody, emotion, phrasing, narrator performance, or acoustic
  synthesis quality.
- Publishing a password or embedding it in source control.
- Making silent semantic changes when a token remains ambiguous.

## 3. Research questions

The research was organized around the following questions:

1. Is there an interoperable standard for pronunciation lexicons?
2. Which established resources cover Mandarin words and pinyin?
3. Which tools address Mandarin polyphone disambiguation?
4. Which established resource covers US-English pronunciations?
5. Which text-normalization systems address numbers, dates, units, and symbols?
6. Can a static lexicon alone support production audiobook synthesis?
7. What license obligations apply to redistributed data?
8. How should uncertainty be exposed rather than hidden?

## 4. Primary evidence reviewed

### W3C Pronunciation Lexicon Specification 1.0

Source: https://www.w3.org/TR/pronunciation-lexicon/

The W3C specification defines a mapping between graphemes, aliases, and
pronunciations for speech synthesis and recognition. It explicitly supports
multiple pronunciations, multiple orthographies, homographs, and acronym
expansion. It also distinguishes pronunciation lookup from the broader TTS
pipeline, which includes text normalization and sentence-level processing.

Engineering consequence: the internal JSON schema follows the same conceptual
separation between written form, spoken alias, phoneme representation, language,
context, and multiple candidate pronunciations.

### CC-CEDICT

Source: https://cc-cedict.org/wiki/

CC-CEDICT supplies a large downloadable Chinese-English dictionary with
traditional forms, simplified forms, numbered-tone pinyin, and definitions.
The project is licensed under CC BY-SA 3.0.

Engineering consequence: CC-CEDICT became the bulk Mandarin word-pronunciation
layer. Its license and attribution remain visible in the packaged documentation.
It is not treated as a complete context-disambiguation engine.

### pypinyin

Source: https://github.com/mozillazg/python-pinyin

pypinyin provides character-to-pinyin conversion, phrase-aware matching,
polyphone support, and extensible dictionaries.

Engineering consequence: phrase-first matching and custom project overrides are
first-class concepts in the release.

### g2pW

Source: https://github.com/GitYCC/g2pW

g2pW is a Mandarin grapheme-to-phoneme converter designed for contextual
polyphone disambiguation. Its published examples distinguish readings such as
the characters in "bank" and "action" from sentence context.

Engineering consequence: the release explicitly recommends contextual G2P
after deterministic phrase matching and before human review. It does not select
the first dictionary reading blindly.

### PaddleSpeech

Source: https://github.com/PaddlePaddle/PaddleSpeech

PaddleSpeech provides a Chinese TTS text frontend and includes g2pW integration,
mixed Chinese-English support, and SSML-related frontend work.

Engineering consequence: the JSON is designed as an engine-neutral source that
can be adapted into a full TTS frontend rather than pretending to be a complete
frontend itself.

### WeTextProcessing

Source: https://github.com/wenet-e2e/WeTextProcessing

WeTextProcessing provides production-oriented Chinese and English text
normalization and inverse text normalization.

Engineering consequence: number, date, time, unit, and symbol handling is
represented as classified normalization rules rather than an uncontrolled list
of string replacements.

### CMU Pronouncing Dictionary

Source: https://github.com/cmusphinx/cmudict

CMUdict is a machine-readable US-English pronunciation dictionary maintained by
Carnegie Mellon University's speech community. It uses ARPAbet with lexical
stress and permits unrestricted research and commercial use while requesting
source acknowledgement.

Engineering consequence: CMUdict became the bulk English pronunciation layer.
Contextual English heteronyms remain a separate curated layer because a
dictionary can list alternatives without deciding which one a sentence needs.

## 5. Findings

### 5.1 No universal static Mandarin oracle exists

Mandarin characters such as 行, 乐, 长, 重, 还, 得, 着, 和, 处, 传, 藏, 调,
解, 薄, and 血 can change pronunciation by word, grammar, meaning, name, or
historical context. A static character-level default can therefore create
confident but incorrect speech.

The correct engineering unit is usually the longest known phrase, followed by a
contextual model for unresolved cases.

### 5.2 English also requires a pronunciation lexicon

English needs a lexicon for at least four reasons:

- spelling-to-sound correspondence is irregular;
- lexical stress can distinguish noun and verb forms;
- heteronyms such as `read`, `lead`, `record`, `wind`, `bass`, and `resume`
  require grammatical or semantic context;
- names, brands, technical abbreviations, and loanwords are frequently outside
  general dictionaries.

CMUdict substantially improves coverage but cannot remove the need for project
overrides and contextual analysis.

### 5.3 Text normalization is a separate production problem

Human readers infer whether `08.14.2021` is a date, whether `3/4` is a fraction
or date fragment, whether `2.1.0` is a software version, and whether a long
number is a quantity or identifier. TTS engines often do not.

The release therefore classifies token roles before verbalization. The same
principle applies to percentages, ratios, scientific notation, temperature,
storage units, mathematical symbols, URLs, email addresses, file paths, and
mixed alphanumeric identifiers.

### 5.4 Uncertainty must become visible output

The safest production behavior is not to guess silently. Ambiguous names,
unresolved date order, unknown acronyms, low-confidence G2P output, and
unclassified numbers should enter a review report.

## 6. Architecture

### Layer 1: manifest and precedence

`pronunciation-lexicon.json` defines processing order, profile locations,
quality gates, project-override structure, and limitations.

### Layer 2: Mandarin core

`pronunciation-lexicon.zh-CN.core.json` contains:

- 413 contextual phrase pronunciations;
- 16 place-name rules;
- 16 surname rules;
- 40 neutral-tone phrases;
- 86 acronym and specialist aliases;
- date, time, number, identifier, unit, and fallback rules.

Pinyin uses numeric tones. Tone `5` represents neutral tone.

### Layer 3: English core

`pronunciation-lexicon.en-US.core.json` contains:

- 66 contextual heteronym groups;
- 51 acronym and specialist aliases;
- 38 abbreviation expansions;
- IPA pronunciation distinctions;
- date, time, number, identifier, unit, and fallback rules.

### Layer 4: bulk Mandarin data

`data/zh-CC-CEDICT-pronunciations.jsonl` contains 125,008 validated JSON Lines
records and 202,831 simplified/traditional grapheme variants.

### Layer 5: bulk English data

`data/en-CMUdict-pronunciations.jsonl` contains 135,166 validated pronunciation
records covering 126,052 normalized headwords.

### Layer 6: schema, documentation, and validation

The package includes a JSON Schema, Chinese and English usage guides, source and
license documentation, and a machine-readable validation report.

## 7. Design decisions

### JSON plus JSON Lines

Small curated layers use formatted JSON for human review. Large external
dictionaries use JSON Lines for streaming, low memory use, incremental indexing,
and line-level validation.

### Longest match first

Phrase entries have priority over individual-character readings. Book-specific
overrides have priority over generic phrase entries.

### Separate aliases from phonemes

Some engines accept spoken aliases but not custom phonemes. Others accept IPA,
pinyin-like alphabets, ARPAbet-like alphabets, or vendor-specific symbols.
Keeping aliases and phoneme data separate allows adapters to choose the safest
supported mechanism.

### Separate language profiles

Chinese and English require different normalization, G2P, stress, and fallback
behavior. A single flat list would make precedence and ambiguity harder to
control.

### Preserve source licenses

The external dictionaries remain attributed and are not presented as original
KR-authored data. The curated architecture, rules, and overrides are separated
from those bulk source layers.

### Human review remains mandatory

The quality gate recommends listening to every title, every project override,
every flagged token, and at least the first and last paragraph of every chapter.

## 8. Production process

1. Reviewed the W3C lexicon model and current open-source Mandarin and English
   resources.
2. Defined a common manifest with language-specific profiles and a strict
   precedence order.
3. Curated high-impact Mandarin phrase overrides for polyphones, place names,
   surnames, neutral tones, historical terms, and mixed-language technical
   vocabulary.
4. Curated English contextual heteronyms, abbreviations, acronyms, specialist
   terms, and pronunciation hints.
5. Added classified date, number, time, unit, symbol, identifier, and scientific
   notation rules.
6. Downloaded current CC-CEDICT and CMUdict source data from their public project
   endpoints.
7. Converted both bulk sources to UTF-8 JSON Lines while retaining attribution
   and source hashes.
8. Generated documentation, schema, project-override templates, and validation
   rules.
9. Parsed every JSON file and every JSON Lines record.
10. Detected and removed duplicate curated phrase entries.
11. Performed targeted spot checks for high-risk Chinese and English readings.
12. Built the final distribution and then produced the Owner-approved encrypted
    release archive.

## 9. Validation evidence

### Structured-data validation

- Main manifest parsed successfully.
- Mandarin core parsed successfully.
- English core parsed successfully.
- JSON Schema parsed successfully.
- All 125,008 Mandarin JSON Lines records parsed individually.
- All 135,166 English JSON Lines records parsed individually.
- Curated Mandarin phrase keys were checked for duplicates.
- English heteronym keys were checked for duplicates.

### Targeted pronunciation checks

Mandarin checks included contrasting readings such as:

- 银行 and 行动;
- 音乐 and 快乐;
- 头发 and 发展;
- 干净 and 干部;
- 爱好 and 好人;
- 正月 and 正确;
- 首都 and 都是;
- 龟裂, 南无, 阿房宫, and selected place names.

English checks included:

- `read`;
- `lead`;
- `record`;
- `wind`;
- `bass`;
- `resume`.

### Archive validation

- ZIP entries: 12 total.
- Directory entries: 2.
- Non-directory entries: 10.
- Encrypted non-directory entries: 10.
- Extraction without a password: rejected as expected.
- Encrypted archive size: 5,591,813 bytes.
- SHA-256: `6AA51E22F00DE23937681E602F6800760DE1079367C8B642FE1BB237798C8FCE`.

## 10. Distribution and security decision

The public repository and GitHub Release publish the encrypted archive and its
checksum. The password is deliberately excluded from:

- source control;
- README content;
- release notes;
- Git tags;
- release asset names;
- checksum files;
- build and validation reports.

Password requests are handled through kr@kairosrepublica.com. This separates public
integrity verification from controlled archive access.

The encryption protects archive access but does not replace the licenses of
included third-party data. Authorized recipients must still follow the included
license notices.

## 11. Relationship to KR Book To Audio 3.0

This is a parallel release rather than a replacement application build.

KR Book To Audio 3.0 provides the long-form workflow: intake, OCR decisions,
text preparation, review, voice selection, preview, resumable synthesis, and
diagnostics.

The pronunciation lexicon provides an additional language-engineering
foundation that can improve the reviewed text before synthesis or support a
future pronunciation adapter in the application.

The two releases remain separately versioned:

- KR Book To Audio - Istanbul Release 3.0;
- KR B2A Pronunciation Lexicon - Istanbul Release 1.0.

## 12. Known limitations and remaining risks

- Static phrase coverage will never include every proper noun, fictional term,
  dialect reading, or new technical expression.
- Some official place and personal names have competing accepted readings.
- Chinese tone sandhi and prosody are not fully represented by dictionary
  pinyin.
- English dialect, stress, and name preferences vary.
- TTS vendors support different SSML and phoneme alphabets.
- ZIP password protection controls access but is not a digital signature.
- A checksum proves byte integrity, not linguistic correctness.
- Every target engine still requires adapter testing and listening review.

## 13. Recommended future work

1. Add a KR Book To Audio adapter that loads project overrides and emits
   engine-specific SSML.
2. Add automated out-of-vocabulary and ambiguity reports before Part 1 preview.
3. Add g2pW-backed Mandarin contextual fallback.
4. Add CMUdict indexing and an English G2P fallback for unknown words.
5. Add per-book pronunciation approval files that are bound to the cleaned-text
   hash.
6. Add regression audio fixtures for dates, numbers, units, Chinese polyphones,
   and English heteronyms.
7. Add dialect profiles such as en-GB and zh-TW only when validated resources
   and review capacity are available.

## 14. Reproducibility record

The release can be audited through:

- the published engineering record;
- the public release notes;
- the SHA-256 receipt;
- the validation report inside the encrypted archive;
- source and license documentation inside the archive;
- the Git commit, tag, and GitHub Release record.

This record intentionally documents evidence, design rationale, implementation
steps, and verification results. It does not claim that a pronunciation
dictionary can eliminate contextual language understanding or human review.
