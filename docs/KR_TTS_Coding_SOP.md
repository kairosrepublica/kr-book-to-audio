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
8. the application restores the task-bound TTS provider, voice, rate, pitch and volume;
9. synthesis resumes directly from the first incomplete Part when proofreading and Part-1 approval remain valid.

Windows keep-awake is enabled by default during long OCR and TTS work. It prevents automatic sleep only.

CLI recovery:

```bash
kr-book-to-audio recent-jobs --rebuild
kr-book-to-audio recover PATH_TO_JOB
```

## Recent-job index safety

Validation and test runs must use an isolated `KR_B2A_APP_ROOT`. The GUI resume panel prunes entries whose job manifest no longer exists and displays only interrupted or incomplete tasks by default.


## Legacy resume boundary

Jobs created before v1.3.2 may not store raw speech controls. The application attempts safe recovery by comparing candidate controls against the stored audio signature. When no exact match exists, it preserves completed MP3 files and asks the operator to regenerate and approve Part 1. Do not bypass that gate.

The default resume panel collapses older resumable attempts for the same source book. Older attempts remain in the rebuildable history index.


## Branding surface

The desktop loads the BA branding assets during startup. Missing optional icon assets must not block text extraction, OCR, TTS or resume. The bottom footer is informational only and must remain visually separated from controls, logs and progress state.


## Legacy resume verification

If a resumable legacy task lacks a complete speech-control snapshot, use the guided voice-check flow. Compare preserved Part 1 with a candidate preview. Approve only when they match closely enough for continuation. Existing MP3 files remain preserved until the Owner approves the rebind.

## Portable release gate — Istanbul Release 2.0

1. Run the full Python regression suite.
2. Build `packaging/KRBookToAudio.spec` with PyInstaller on Windows.
3. Verify the PE subsystem is Windows GUI, not console.
4. Verify the EXE embeds the BA icon.
5. Relocate the onedir folder into a path containing spaces.
6. Run hidden `--portable-smoke-test` mode.
7. Push scoped main delta.
8. Wait for Linux and Windows GitHub Actions jobs to turn green.
9. Create tag and GitHub Release only after remote CI green.
10. Upload portable ZIP and SHA-256 sidecar.
11. Generate the complete integer-Release AI co-coder takeover ZIP.

## PyInstaller src-layout spec rule

For the portable Windows build:

```text
SPECPATH is the directory containing packaging/KRBookToAudio.spec.
Resolve the project root with exactly one parent traversal.
Insert the src directory into sys.path before collect_data_files() runs.
```

This prevents an off-by-one entrypoint path and ensures package data is collected from the src-layout package.
## Export finalization gate

A Book To Audio job is not externally complete merely because all internal Part MP3 checkpoints exist.

After successful full synthesis or successful retry completion:

```text
1. create `<Export root>/<job>/parts`
2. atomically copy every validated internal Part MP3
3. verify exact continuous filenames
4. verify non-empty readable MP3 files
5. verify SHA-256 against authoritative checkpoints
6. write `export_manifest.json` only after PASS
7. announce `Export completed` only after PASS
```

For completed legacy jobs with empty export folders, use **9. Verify export** or:

```bash
kr-book-to-audio finalize-export PATH_TO_JOB
kr-book-to-audio verify-export PATH_TO_JOB
```

Do not regenerate TTS when trusted internal checkpoints are sufficient.
