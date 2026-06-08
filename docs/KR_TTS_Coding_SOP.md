# KR Book To Audio Operator SOP

## Scope

Use this workflow for continuous prose. Do not use it for books whose meaning depends on tables, formulas or figures unless information loss is acceptable.

## Desktop workflow

```bash
kr-book-to-audio-gui
```

Then:

1. Select a source.
2. Run **Analyze source** in OCR analysis.
3. When OCR is required, preview sample OCR and run the recommended local provider.
4. Keep **Auto detect · recommended** unless you have a reason to override the processing profile.
5. Prepare text.
6. Review cleanup recommendations. Apply only the action buttons you accept.
7. Open and review cleaned text.
8. Approve reviewed text and rebuild.
9. Refresh voices if needed, audition the selected voice and generate Part 1.
10. Approve Part 1 after listening.
11. Synthesize all parts, retry recorded failures and merge only after validation.

## OCR policy

Prefer native text. Do not OCR reliable text layers merely because OCR is available.

The advisor discovers local providers and recommends automatically. Cloud adapters are reserved but disabled. The program does not upload pages to OpenAI, Anthropic or any custom endpoint in this release.

## Provider-extension policy

OCR and TTS adapters share explicit contracts. Future API implementations must read credentials from environment variables or an Owner-local secret store. Never place API keys in manifests, logs, source code, GitHub files or command-line history.

## Cleanup policy

Cleanup analysis distinguishes:

```text
not-needed
recommended
review-required
```

Action buttons remove only high-confidence candidates. Review-required repeated text remains untouched.

## Recovery

Re-run failed parts against the same job directory. Valid manifest-matched MP3 files are reused. Invalid, modified or stale files are regenerated.
