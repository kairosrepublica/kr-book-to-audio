# KR Book To Audio 3.0 — Development / Upgrade Record and GitHub Commit Handoff

**Document purpose:** detailed development record for the current long debugging conversation, plus explicit handoff instructions for the next AI co-coder to commit this record to GitHub.
**Generated:** 2026-06-14
**Project:** KR Book To Audio 3.0
**Audience:** AI co-coder continuing in a new conversation
**Classification:** SANITIZED-INTERNAL. Local Windows paths and temporary workspace paths have been redacted for GitHub commit.

---

## 0. Owner's latest binding instruction

The Owner's binding correction after the V35–V43 failure loop:

```text
1. Only change the extremely simple UI-related code that actually needs to change.
2. Do not introduce unnecessary verification, cross-checking, fixture layers, broad gates, or unrelated code.
3. Delete errors caused by the previous AI before continuing.
4. The previous conversation is too long and unreliable; continue from this handoff in a clean new conversation.
```

The next co-coder must treat this as the controlling scope boundary.

---

## 1. KREC boot context for the next co-coder

### 1.1 Required KREC authority files

Before any engineering mutation, load and follow the current KR Engineering Codex authority pack:

```text
01_KR_Engineering_Codex_START_HERE.md
02_KR_Engineering_Codex_Governance_CONSTITUTION.md
03_KR_Engineering_Codex_General_Core_RULES.md
04_KR_Engineering_Codex_SOP_Library.md
05_KR_Engineering_Codex_Master_CHECKLIST.md
06_KREC_REGISTRY_Verified_Implementations_And_Golden_Examples.md
KREC_Local_Environment_PROFILE_PRIVATE.md
KREC_ERROR_Index_PRIVATE.md
KREC_AUTHORITY_PACK_MANIFEST_PRIVATE.md
```

Known authority pack in this conversation:

```text
KREC-PACK-v3.4.0-20260611-001
```

### 1.2 Classification

For any code change after this handoff:

```text
KREC_MUTATION
```

But the scope must stay narrow:

```text
minimal UI-only correction or documentation-only commit
```

### 1.3 Required first audit in new chat

The next co-coder should begin with:

```text
KREC_BOOT_AUDIT
- Authority pack loaded: PASS/FAIL
- Request class: KREC_MUTATION or KREC_LITE if only committing this documentation
- Target repo verified: PASS/FAIL
- Public/private boundary: private unless Owner explicitly asks sanitized public commit
- Next action: verify real repository/current source before mutation
```

---

## 2. High-level project goal

KR Book To Audio is a Windows GUI application for turning books/PDFs/text into audio, with:

```text
- Chinese-optimized workflow
- OCR engine selection and local OCR support
- TTS provider selection
- Durable resume
- Part-by-part audio synthesis
- GUI status/progress reporting
- portable Windows EXE distribution
- no black console flashing
```

Owner priorities in this conversation were practical UI usability and release stability, not broad architectural redesign.

---

## 3. Most important current technical truth

The actual user-visible issue that triggered the late V37–V43 loop was small:

```text
During audio synthesis, the Status panel's current-row Status column does not live-update its percent reliably.

Top text above the progress bar: correct, e.g. Part 010 / 018 | 067%
Main progress bar: correct
Status Treeview row: often stuck at 5% or jumps to 100%
```

The intended minimal runtime behavior is:

```python
# conceptual only
parts = getattr(self, "parts", None)
if parts is not None:
    self._set_part_state(index, f"{percent}%", highlight="running")
    self._center_part_status(index)
```

Important nuance:

```text
- Real GUI Treeview should receive the current-row percent update.
- Bare/partial App test fixtures without `self.parts` should not receive fake `_set_part_state(...)` side effects.
- Do not refresh the whole job view for high-frequency telemetry.
```

---

## 4. What must not be touched without new Owner approval

The following areas were explicitly out of scope during the late repair loop and must remain frozen unless the Owner reopens them:

```text
OCR implementation
OCR workflow UI
TTS provider implementation
Voice sample logic
Reload behavior
Reject behavior
Resume interrupted jobs
Save Job behavior / removed Save Job button
Audio Status single-line template
Provider telemetry mailbox
Window layout, size, colors, fonts, palette
Portable packaging / release flow
Git/GitHub publication mechanics, unless the task is documentation-only commit
Universal KREC Codex documents
```

---

## 5. Chronological development / upgrade record from this conversation

This section records the main V8–V43 sequence visible in the conversation. Some early artifacts were produced as delivery ZIP/script pairs and were not all re-opened in this final pass. Treat this as a development log, not as proof that each version is a valid current baseline.

| Stage | Artifact / version label | Main intent | Status / lesson |
|---|---|---|---|
| Initial handoff | `20260612_0055_KR_BOOK_TO_AUDIO_v2_95_0_AI_COCODER_HANDOFF.zip` | Starting co-coder handoff for v2.95 line. | Baseline context only. |
| HTML prototype | `20260612_0110_KR_BOOK_TO_AUDIO_UI_REDESIGN_HTML_PROTOTYPE_v1.html/png` | Visual redesign prototype. | UI guidance only, not runtime source truth. |
| V8 | `V8_UI_SHELL_AND_VOICE_PREVIEW_CLOSURE` | UI shell and voice preview closure. | Early closure attempt. |
| V9 | `V9_RELOAD_VARIANT_AND_COLLECT_ALL_REPAIR_CLOSURE` | Reload variant and collect-all repair. | Start of stronger collect-all orchestration. |
| V10 | `V10_IDEMPOTENT_UI_DOMAIN_AND_BACKPRESSURE_CLOSURE` | UI idempotence and event backpressure. | Backpressure became recurring domain. |
| V11 | `V11_BYTECODE_QUARANTINE_AND_STALE_PYC_CLOSURE` | Stale `.pyc` and bytecode quarantine. | Prevented stale bytecode false signals. |
| V12 | `V12_EXACT_FIXTURE_DOMAIN_MIGRATION_CLOSURE` | Exact fixture/domain migration. | Fixture domain discipline introduced. |
| V13 | `V13_OWNER_UPPERCASE_FOOTER_SPEC_RESTORATION` | Restore Owner footer casing/spec. | UI spec restoration. |
| V14 | `v2.96.0 V14_HTML_APPROVED_UI_REBUILD_AND_LOCALE_SAMPLE_FIX` | Rebuild approved HTML UI and locale sample fix. | Larger UI rebuild step. |
| V15 | `v2.96.1 V15_WHOLE_UI_FIXTURE_DOMAIN_MIGRATION` | Whole UI fixture-domain migration. | Tests started to become more complex. |
| V16 | `v2.96.2 V16_RESIDUAL_FIXTURE_DOMAIN_CLOSURE` | Residual fixture-domain closure. | Fixture cleanup. |
| V17 | `v2.97.0 V17_WINDOWS_DEFAULT_UX_AND_STRICT_NATIVE_VOICE_SAMPLES` | Windows default UX and strict native voice sample behavior. | UI defaults / voice samples. |
| V18 | `v2.97.1 V18_RESIDUAL_MIGRATION_IDEMPOTENCE_CLOSURE` | Residual migration idempotence. | Migration stabilization. |
| V19 | `v2.97.2 V19_META_FIXTURE_FALSE_POSITIVE_CLOSURE` | Meta-fixture false positive closure. | Important validator lesson: avoid false positives. |
| V20 | `v2.98.0 V20_WORKFLOW_STATUS_AND_RELOAD_STATE_MACHINE_CLOSURE` | Workflow Status and reload state-machine closure. | Workflow status expanded. |
| V21 | `v2.98.1 V21_RESIDUAL_UI_CONTRACT_ALIGNMENT` | Residual UI contract alignment. | Continued UI contract tuning. |
| V22 | `v2.98.2 V22_SINGLE_CANONICAL_FIXTURE_WRITER_CLOSURE` | Single canonical fixture writer closure. | Tried to reduce writer conflicts. |
| V23 | `3.0 V23_HARD_CANCELLATION_WINDOW_STATE_AND_OCR_TRUTH` | Hard cancellation, window state, OCR truth. | Runtime cancellation/OCR truth area. |
| V24 | `3.0 V24_TELEMETRY_BACKPRESSURE_AND_STARTUP_PROBE` | Telemetry backpressure and startup probe. | Backpressure evidence increased. |
| V25 | `3.0 V25_OFFLINE_VISIBILITY_FIXTURE_JURISDICTION` | Offline visibility and fixture jurisdiction. | Jurisdiction issue emerged. |
| V26 | `3.0 V26_RUNTIME_CANCELLATION_OCR_PROGRESS_AND_SAVE_JOB` | Runtime cancellation, OCR progress, Save Job. | Later Save Job removal issue. |
| V27 | `3.0 V27_SINGLE_CANONICAL_RUNTIME_WRITER_AND_SEMANTIC_OCR_FIXTURE` | Single runtime writer and semantic OCR fixture. | Runtime writer discipline. |
| V28 | `3.0 V28_SAFE_RELOAD_UI_TEXT_PREPARE_WATCHDOG_AND_DIALOG_PLACEMENT` | Safe reload UI, text prepare watchdog, dialog placement. | UI / watchdog correction. |
| V29 | `3.0 V29_VALIDATOR_JURISDICTION_FINAL_CLOSURE` | Validator jurisdiction final closure. | Avoid validator overreach. |
| V30 | `3.0 V30_CLEANUP_ALIGNMENT_AND_AUDIO_STATUS_ANTI_JITTER` | Cleanup alignment and Audio Status anti-jitter. | Directly relevant to UI status jitter. |
| V31 | `3.0 V31_REMOVE_SAVE_AND_SINGLE_AUTHORITY_AUDIO_STATUS` | Remove Save Job and enforce single-authority Audio Status. | Important desired state: Save button removed; audio status single-line. |
| V32 | `3.0 V32_FULL_GRAPH_IDEMPOTENCE_AND_LIGHTWEIGHT_TELEMETRY` | Full graph idempotence and lightweight telemetry. | Likely most important stable local acceptance candidate; Owner later asked for V32 source. |
| V33 | `3.0 V33_PARTIAL_APP_REACHABILITY_AND_FIXTURE_DOMAIN` | Partial App reachability and fixture-domain closure. | Partial App fixture compatibility. |
| V34 | `3.0 V34_OPTIONAL_LOG_SINK_REACHABILITY` | Optional log sink reachability. | Reduced direct widget assumptions. |
| V35 | `3.0 V35_PROVIDER_TELEMETRY_FIXTURE_JURISDICTION` | Provider telemetry fixture jurisdiction. | Later became stale fixture conflict. |
| V36 | `3.0 V36_RUN_LOG_TIMESTAMP_RESTORATION_AND_V35_FIXTURE` | Full datetime timestamp restoration in Run log. | Timestamp format restored, but fixture layering continued. |
| V37 | `3.0 V37_STATUS_TREE_ROW_PERCENT_LIVE_UPDATE` | Status Treeview row percent live update. | Actual UI issue targeted, but partial App guard was initially wrong. |
| V38 | `3.0 V38_MINIMAL_STATUS_TREE_AND_LOG_FIXTURE` | Minimal status tree/log fixture closure. | Improved guard but inherited fixture conflicts remained. |
| V39 | `3.0 V39_BACKPRESSURE_FIXTURE_TREEVIEW_CONTRACT` | Align backpressure fixture with current Treeview row update. | Caused V35 stale fixture conflict. |
| V40 | `3.0 V40_V35_STALE_FIXTURE_EXPECTATION` | Attempt to close V35 stale fixture expectation. | Still wrong / insufficient. |
| V41 | `3.0 V41_MINIMAL_V35_FIXTURE_ONLY` | Attempt to fix only V35 fixture. | Affected test still failed; wrong target/state. |
| V42 | `3.0 V42_DELETE_AI_CAUSED_TEST_ERRORS_MINIMAL_UI_ONLY` | Delete AI-caused test errors and return to minimal UI-only. | Failed because test harness missed `PYTHONPATH=source\src`. |
| V43 | `3.0 V43_MINIMAL_CLEANUP_AND_PYTHONPATH_FIX` | Fix V42 harness PYTHONPATH and run affected test. | Affected `test_gui_event_backpressure_v241` passed: 10 tests OK. Not a full release gate. |

---

## 6. Latest verified facts after V43

The Owner ran V43 directly in Windows PowerShell:

```powershell
python "$env:USERPROFILE\Downloads\20260614_0148_KR_BOOK_TO_AUDIO_3_0_V43_MINIMAL_CLEANUP_AND_PYTHONPATH_FIX.py"
```

The script reported:

```json
{
  "mode": "v43-minimal-cleanup-and-pythonpath-fix",
  "source": "<TEMP_PATH>
  "affected_test": {
    "ok": true,
    "cmd": [
      "C:\\Users\\Kentr\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
      "-m",
      "unittest",
      "tests.test_gui_event_backpressure_v241"
    ],
    "pythonpath_prefix": "<TEMP_PATH>
    "returncode": 0,
    "stderr_tail": "..........\n----------------------------------------------------------------------\nRan 10 tests in 0.059s\n\nOK\n"
  },
  "ok": true
}
```

Interpretation:

```text
V43 proves only the minimal affected legacy backpressure test passed.
It does not prove full regression.
It does not prove final packaged EXE.
It does not prove the correct canonical project root.
It does not prove GitHub state.
```

---

## 7. Critical mistake to avoid: do not continue from the wrong temp path blindly

The last failed guidance from the previous AI was telling the Owner to launch from:

```text
<OWNER_HOME>\AppData\Local\Temp\kr-b2a-v300-release-v35-20260613_221723\source
```

This is only a temporary repair/source workspace from the scripts. It may not be the canonical project directory or the final executable location.

The next co-coder must discover and verify the real project root and release artifact before any launch/run/commit advice.

---

## 8. V32 source-code request context

After the V43 failure-loop cleanup, the Owner asked for source code for:

```text
KR_Book_To_Audio_Local_Acceptance_3.0_RELEASE_V32_20260613_221853
```

The previous AI did not have the actual V32 ZIP/source tree in the sandbox. It generated a local packager script instead:

```text
20260614_0236_KR_BOOK_TO_AUDIO_V32_SOURCE_CODE_PACKAGER.py
20260614_0236_KR_BOOK_TO_AUDIO_V32_SOURCE_CODE_PACKAGER_DELIVERY.zip
```

Expected output when run on the Owner machine:

```text
KR_Book_To_Audio_Local_Acceptance_3.0_RELEASE_V32_20260613_221853_SOURCE_CODE.zip
```

The next co-coder should ask the Owner to upload the generated V32 source ZIP if continuing from V32. Do not assume the V32 source is available in the new chat unless it is attached.

---

## 9. Recommended clean continuation strategy

### 9.1 Best baseline choice

Given the V35–V43 fixture pollution, the safest continuation is:

```text
Start from V32 source if the Owner can provide it.
Do not continue from V35–V43 unless there is a verified reason.
```

Reason:

```text
V32 is the Owner-named local acceptance release.
V35–V43 contained AI-caused fixture churn around a simple UI bug.
```

### 9.2 Minimal next technical action if continuing the UI issue

1. Verify actual source root.
2. Open `src/kr_book_to_audio/gui.py`.
3. Locate the code path that updates current part status during provider telemetry / estimate tick.
4. Add or verify a guard so Treeview updates only when the real `self.parts` Treeview exists.
5. Run only the existing affected lightweight unit test first:

```powershell
$env:PYTHONPATH = "<SOURCE_ROOT>\src"
python -m unittest tests.test_gui_event_backpressure_v241
```

6. Then launch the real app only after source root is confirmed.
7. Have the Owner visually check that the Status column percentage moves during a short synthesis task.

No new test files should be added unless the existing test cannot protect the exact bug.

---

## 10. Commands for repository/source discovery in new chat

The next co-coder should use non-mutating discovery first.

Suggested Windows PowerShell discovery commands:

```powershell
$roots = @(
  "$env:USERPROFILE\OneDrive\Documents\KRG\KRG Code\04_KR_Book_To_Audio",
  "$env:USERPROFILE\OneDrive\Documents\KRG\KRG Dock\KRG Dev",
  "$env:USERPROFILE\Downloads",
  "$env:LOCALAPPDATA\Temp"
) | Where-Object { Test-Path $_ }

Get-ChildItem -Path $roots -Recurse -File -Filter "kr_book_to_audio_gui.py" -ErrorAction SilentlyContinue |
  Select-Object FullName, LastWriteTime |
  Sort-Object LastWriteTime -Descending |
  Format-Table -AutoSize

Get-ChildItem -Path $roots -Recurse -File -Filter "KRBookToAudio.exe" -ErrorAction SilentlyContinue |
  Select-Object FullName, LastWriteTime, Length |
  Sort-Object LastWriteTime -Descending |
  Format-Table -AutoSize
```

Repository verification commands before any commit:

```powershell
git rev-parse --show-toplevel
git branch --show-current
git remote -v
git status --short
git log -1 --oneline
```

---

## 11. GitHub commit handoff for this documentation record

The Owner asked to organize all development/upgrade records from this conversation into a detailed Markdown document and hand it to an AI co-coder to commit to GitHub.

### 11.1 Commit boundary

This handoff is a documentation-only commit. It should not include runtime code changes.

Recommended path inside the repository:

```text
docs/dev-history/20260614_KR_BOOK_TO_AUDIO_3_0_DEV_UPGRADE_RECORD_AFTER_V43.md
```

If the repository is public, use a sanitized version instead, removing or redacting:

```text
<OWNER_HOME>\...
AppData\Local\Temp\...
private Project Source filenames if not intended for publication
private KREC authority pack details beyond generic references
```

If the repository is private, this document can be committed as-is at Owner discretion.

### 11.2 Suggested commit message

```text
docs: record KR Book To Audio 3.0 V32-V43 debug history
```

### 11.3 Suggested commit procedure for AI co-coder

Do not run these until the repository root, branch, remote, and public/private boundary are verified.

```powershell
# from verified repository root
New-Item -ItemType Directory -Force -Path "docs\dev-history" | Out-Null
Copy-Item -LiteralPath "<PATH_TO_THIS_MD>" -Destination "docs\dev-history\20260614_KR_BOOK_TO_AUDIO_3_0_DEV_UPGRADE_RECORD_AFTER_V43.md" -Force

git status --short
git diff -- docs/dev-history/20260614_KR_BOOK_TO_AUDIO_3_0_DEV_UPGRADE_RECORD_AFTER_V43.md

git add docs/dev-history/20260614_KR_BOOK_TO_AUDIO_3_0_DEV_UPGRADE_RECORD_AFTER_V43.md
git diff --cached --check
git commit -m "docs: record KR Book To Audio 3.0 V32-V43 debug history"
git push
```

### 11.4 Commit refusal conditions

The co-coder must stop before commit if any of the following is true:

```text
repository root is not verified
remote URL is not verified
branch is not verified
working tree has unrelated changes and Owner has not approved staging only this file
public/private boundary is unclear
Owner actually wants a code commit, not documentation-only commit
```

---

## 12. Known failure families from this conversation

| Failure | What happened | Prevention |
|---|---|---|
| Fixture cascade | New tests were added to fix old tests, creating V35–V43 churn. | Do not add new fixtures for a tiny UI sync bug; use existing affected test. |
| Wrong target file | V41 patched the V35 fixture while `test_gui_event_backpressure_v241.py` remained the affected runtime fixture. | Inspect actual failing traceback and edit only the failing file if needed. |
| Missing `PYTHONPATH` | V42 failed because `kr_book_to_audio` could not be imported. | Set `PYTHONPATH=<source>\src` for src-layout tests. |
| Temp path overclaim | Previous AI gave launch instructions for a temp source workspace as though it were the real app. | Verify canonical project root and EXE before launching. |
| Validation overreach | Broad gates and fixture layers were introduced against the Owner's explicit minimal UI request. | Proportionate validation only. |
| Evidence overclaim | Affected unit test pass was treated too close to release confidence. | State evidence tier honestly. |

---

## 13. Current recommended next action list

For the next co-coder:

```text
1. Load KREC authority files.
2. Return compact KREC_BOOT_AUDIT.
3. Clarify whether the immediate task is:
   A. commit this development record to GitHub only, or
   B. continue debugging KR Book To Audio UI.
4. If A: verify repo and commit this document only.
5. If B: ask Owner to upload V32 source ZIP or verify real project root.
6. Do not mutate runtime until source root is verified.
7. Do not add tests unless necessary.
8. Do not package until Owner confirms UI behavior or asks for a portable release.
```

---

## 14. Exact summary for the new AI co-coder

```text
The previous conversation became unreliable due to a long failure loop. The Owner wanted a simple UI fix: update the Status Treeview row percentage during audio synthesis. The previous AI overbuilt validation and created V35–V43 fixture pollution. V43 only proved the affected legacy backpressure unit test now passes when PYTHONPATH is set; it did not prove final GUI behavior or executable location. The Owner then asked for V32 source and finally asked for this complete development record to be handed to a new AI co-coder for GitHub commit. Start clean. Verify repo/source path. Keep scope minimal. Commit this document only if public/private boundary is clear.
```
