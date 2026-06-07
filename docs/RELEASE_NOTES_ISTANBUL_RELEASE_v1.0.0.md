# Istanbul Release v1.0.0

The founding public release of KR Book To Audio establishes a robust local book-to-audiobook foundation with additional safeguards for Chinese-language books.

Highlights:

- one shared Python core for the command-line and Tkinter desktop interfaces;
- automatic general-prose and Chinese-optimized cleaning modes;
- Chinese PDF whitespace normalization, running-header removal and conservative reflow;
- proofread and Part-1 listening gates before full synthesis;
- transparent pronunciation replacement dictionary with preview counts;
- manifest-driven resumability and stale-output invalidation;
- atomic MP3 generation, `ffprobe` validation and strict complete-sequence merge;
- numeric ordering beyond 99 audio parts;
- PDF, EPUB, MOBI/PalmDOC-compatible AZW or PRC, DOCX, TXT and Markdown input;
- deliberate AZW3 rejection until a verified Kindle Format 8 fixture exists.

Deferred extensions include integrated OCR, paid speech backends, semantic chapter extraction, M4B export and offline synthesis.
