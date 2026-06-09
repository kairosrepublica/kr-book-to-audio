# Istanbul Release v2.3.3

## Scope

This patch closes the Owner-machine Windows outer-scroll acceptance failure from v2.3.2.

## Product-local correction

- Resolve the visible top-level Windows shell height in physical screen pixels through Desktop Window Manager extended frame bounds.
- Stop using Tk toolkit height as the Windows authority for the 1870 px physical boundary.
- Hide the outer workflow scrollbar, reset the outer Canvas to the top and consume ordinary outer wheel events when the physical visible shell height is at least 1870 px.
- Restore the outer scrollbar and ordinary outer scrolling below 1870 px.
- Preserve native scrolling priority inside Run log, Recent jobs, Part status, Listbox and Combobox controls.
- Preserve the Footer outside the scroll viewport.

## Frozen systems

SQLite durable state, Resume, OCR, TTS and quiet export remain unchanged.

## Validation

Publication requires:

```text
STATIC_SCAN
REAL_LOCAL_FIXTURE
TARGET_RUNTIME_FIXTURE — real Windows outer-scroll interaction probe
TARGET_RUNTIME_FIXTURE — relocated portable hidden smoke
REMOTE_STATE_VERIFIED — origin/main, CI, tag and Release
OWNER GUI ACCEPTANCE — final visual confirmation
```

Mocked mode-decision tests are supplemental only and cannot close the GUI behavior contract.
