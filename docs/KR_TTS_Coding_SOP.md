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

For completed legacy jobs with empty export folders, the desktop repairs and verifies export automatically when the job is loaded or its output folder is opened. CLI recovery remains available:

```bash
kr-book-to-audio finalize-export PATH_TO_JOB
kr-book-to-audio verify-export PATH_TO_JOB
```

Do not regenerate TTS when trusted internal checkpoints are sufficient.

## Silent child-process policy — Istanbul Release v2.1.0

Desktop operations must launch console-style external tools through `src/kr_book_to_audio/subprocess_utils.py`. On Windows the adapter suppresses child console windows. Do not introduce raw `subprocess.run()` or `subprocess.Popen()` calls for governed CLI tools in pipeline modules.

Governed tools include:

```text
pdfinfo
pdffonts
pdftotext
pdftoppm
ffprobe
ffmpeg
tesseract
ocrmypdf
```

Visible user actions remain separate: Explorer, opening cleaned text and playing MP3 previews.

## Workflow UI policy — Istanbul Release v2.1.0

The desktop layout follows the operating sequence:

```text
Paths
Resume interrupted or incomplete jobs
Text and speech settings
OCR
Text process
Audio process
Runtime monitor
Footer
```

Button state is derived from authoritative manifest state, not click history. Manual export verification is not a normal user step. Manual folder recovery belongs only under Advanced recovery.

## Istanbul Release v2.3.0 state discipline

```text
SQLite is authoritative for resumable mutable state.
JSON is a derived readable snapshot.
MP3 files remain filesystem artifacts with SHA-256 receipts.
Never silently overwrite a newer state revision.
Never delete legacy evidence during migration.
```

Export verification should reuse trusted receipts and avoid redundant ffprobe launches while preserving hash, count, continuity and readability guarantees.

## Desktop fixed-shell and wheel-scroll gate

For every desktop-shell mutation:

1. Keep the copyright and Constantinople signature Footer outside the scroll viewport.
2. Verify that scrolling changes only the internal workflow surface.
3. Use a deterministic 1200 px default width and a 1150 px minimum width.
4. Use exactly 1870 px initial height when the active screen height exceeds 1870 px.
5. Hide the outer scrollbar and disable ordinary outer wheel routing whenever the actual window height is at least 1870 px.
6. Restore the outer scrollbar and ordinary outer wheel routing only when the actual window height falls below 1870 px.
7. Clamp smaller-screen heights to the active display with a safety margin.
8. Route mouse-wheel and touchpad events to the outer viewport only when the hovered inner widget does not own native scrolling.
9. Preserve native scrolling for Run log, Recent jobs, Part status, Listbox and Combobox controls.


## Windows physical-pixel fixed-shell release gate — Istanbul Release v2.3.3

1. Treat the 1870 px fixed-shell boundary as a physical visible-window contract.
2. On Windows, resolve visible top-level shell height through Desktop Window Manager extended frame bounds.
3. Do not compare Tk toolkit coordinates directly against a physical-pixel contract.
4. When fixed mode is active, reset the outer Canvas to the top, hide the outer scrollbar and consume ordinary outer wheel events.
5. Preserve native inner-widget scrolling priority before outer-event suppression.
6. Run the real Windows outer-scroll interaction probe before commit and publication.
7. Treat mocked decision tests as supplemental evidence only.

## v2.4.0 provider resilience and deliverable rules

```text
1. Treat online synthesis as a streamed operation, not an opaque save call.
2. Emit truthful stage, elapsed, received-byte and last-audio-age telemetry.
3. Enforce a no-audio watchdog and a bounded total-Part watchdog.
4. Retry deterministically and surface an actionable Provider-switch recommendation.
5. Never silently switch Provider inside an audiobook job. Provider change invalidates Preview approval.
6. Keep local TTS runtimes and model caches outside OneDrive under C:\dev\KR_TTS_Local.
7. Keep the user-facing Export folder flat: MP3 files plus one reviewed cleaned-text TXT only.
8. Keep machine-facing export receipts, manifests, logs and checkpoints internal under _work.
9. Refuse destructive overwrite when legacy export flattening finds conflicting files.
10. Export sanitized diagnostics without book text, MP3 files, credentials or unnecessary absolute paths.
```

## Local Provider runtime compatibility gate

Before installing a Local Provider dependency, verify its Python compatibility range. Kokoro 0.9.4 requires Python `>=3.10,<3.13`. When the Owner system Python is 3.13 or newer, provision an isolated `uv`-managed Python 3.12 runtime under `C:\dev\KR_TTS_Local` and recreate only the incompatible Kokoro virtual environment. Do not modify the Owner global Python installation.

## Local TTS resource acquisition SOP

1. Use an explicit online-acquisition subprocess environment with inherited offline-only flags overridden.
2. Acquire reusable wheels and model snapshots into the Owner-private `_Resource\KR_TTS_Offline_Resources` archive first.
3. Generate SHA-256 receipts and a resource manifest.
4. Deploy verified Kokoro snapshots into `C:\dev\KR_TTS_Local`.
5. Run the Kokoro worker with offline mode enforced.
6. Never treat pip cache, AppData, Temp or the rebuildable runtime copy as the authoritative archive.

## Windows-safe Hugging Face model staging

1. Set `HF_HUB_DISABLE_SYMLINKS=1` during acquisition.
2. Stage model downloads under the governed `_Resource` archive, not an ephemeral Temp directory.
3. Preserve incomplete staging data after a failed acquisition so a later run can resume.
4. Promote only complete verified snapshots into the formal archive.
5. Delete the staging tree only after formal archive promotion succeeds.

## v2.4.1 GUI responsiveness gate

1. Never forward every low-level Provider chunk into an unbounded Tkinter queue.
2. Store high-frequency telemetry as latest-only snapshots with fixed memory.
3. Keep ordered terminal and control transitions in a separate bounded queue.
4. Limit both event count and elapsed milliseconds in every GUI drain callback.
5. Yield back to the Tk main loop after every bounded drain cycle.
6. Do not perform full job-view refreshes for telemetry-only changes.
7. Snapshot Tkinter control values on the GUI thread before starting background workers.
8. Dispatch Preview playback from a GUI success callback only once.
9. Emit heartbeat telemetry for long-running Kokoro Local worker execution.
10. Terminate and then kill a hung local worker after the bounded deadline.
11. Require the packaged Windows GUI responsiveness probe before Release.
