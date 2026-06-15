# KR B2A Pronunciation Lexicon - Istanbul Release 1.0

This is an important parallel release for KR Book To Audio - Istanbul Release
3.0. It packages a reusable pronunciation and text-normalization foundation for
Chinese, English, and mixed-language audiobook preparation.

## Release purpose

Long-form TTS quality depends on more than a large word list. The source text
must also distinguish dates from decimals, identifiers from quantities,
acronyms from ordinary words, Chinese polyphones from default character
readings, and English heteronyms from spelling-only guesses.

This release provides a layered resource for those tasks:

- a language-neutral processing manifest and quality gate;
- a Mandarin core with contextual phrase readings, neutral tones, surnames,
  place names, acronyms, dates, numbers, units, and fallback policy;
- a US-English core with heteronyms, abbreviations, acronyms, IPA hints,
  dates, numbers, units, and fallback policy;
- full CC-CEDICT-derived Chinese word-to-pinyin records;
- full CMUdict English word-to-ARPAbet records;
- schema, source, license, usage, and validation documentation.

## Coverage

| Layer | Validated count |
|---|---:|
| Mandarin contextual phrase overrides | 413 |
| Mandarin place-name rules | 16 |
| Mandarin surname rules | 16 |
| Mandarin neutral-tone phrases | 40 |
| Mandarin acronym and specialist aliases | 86 |
| CC-CEDICT-derived pronunciation records | 125,008 |
| Simplified/traditional grapheme variants | 202,831 |
| English contextual heteronym groups | 66 |
| English acronym and specialist aliases | 51 |
| English abbreviation expansions | 38 |
| CMUdict pronunciations | 135,166 |
| CMUdict normalized headwords | 126,052 |

## Encrypted archive

Release asset:

`kr-b2a-universal-pronunciation-lexicon-istanbul-release-1.0.zip`

The ZIP is intentionally encrypted. All 10 non-directory entries carry the ZIP
encryption flag and extraction without a password was verified to fail.

To request the password, email [kr@kairosrepublica.com](mailto:kr@kairosrepublica.com).
The password is not stored in the repository, release notes, release metadata,
or checksum receipt.

SHA-256:

`6AA51E22F00DE23937681E602F6800760DE1079367C8B642FE1BB237798C8FCE`

## Recommended integration

Use this precedence order:

`book-specific overrides > confirmed entities > contextual phrases > acronyms
and abbreviations > text normalization > bulk dictionary > contextual G2P >
human listening review`

Most TTS engines do not consume this JSON format directly. An adapter should
convert spoken aliases into text replacements or SSML and map pinyin, IPA, or
ARPAbet to the target engine's supported phoneme alphabet.

## Important limitations

- No static dictionary can resolve every Chinese polyphone without context.
- No static English dictionary can resolve all heteronyms, names, dialects,
  loanwords, and stress variants.
- Tone sandhi, prosody, erhua, fictional terms, historical readings, and
  publisher preferences may require project-specific overrides.
- The lexicon improves text preparation but does not replace chapter-level
  listening review before full audiobook synthesis.

## Licensing

The archive preserves source and license documentation.

- CC-CEDICT-derived data remains subject to CC BY-SA 3.0.
- CMUdict permits unrestricted research and commercial use and requests
  attribution to Carnegie Mellon University.

## Related engineering record

See:

`docs/dev-history/KR_B2A_PRONUNCIATION_LEXICON_1_0_ENGINEERING_RECORD.md`
