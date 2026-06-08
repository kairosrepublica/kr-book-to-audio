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

## Durable resume and Recent jobs

Long TTS tasks are resumable at Part granularity. The authoritative state lives in each job manifest. The global `execution_history.json` file is only a rebuildable index for recent-job navigation.

When a prior process ended unexpectedly:

1. relaunch the desktop application;
2. select the interrupted row under **Recent jobs**;
3. click **Resume selected**;
4. the application verifies that the prior PID is dead before clearing a stale lock;
5. residual `.partial.mp3` files are removed;
6. completed MP3 records are revalidated;
7. only sidecar-bound orphan MP3 files with matching text and audio signatures are adopted;
8. synthesis resumes from the first incomplete Part when proofreading and Part-1 approval remain valid.

Windows keep-awake is enabled by default during long OCR and TTS work. It prevents automatic sleep only.

CLI recovery:

```bash
kr-book-to-audio recent-jobs --rebuild
kr-book-to-audio recover PATH_TO_JOB
```
