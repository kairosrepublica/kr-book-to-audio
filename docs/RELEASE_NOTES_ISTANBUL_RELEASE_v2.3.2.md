# Istanbul Release v2.3.2

This product-local precision desktop-shell patch keeps the v2.3.1 fixed Footer and the v2.3.0 SQLite durable-state engine unchanged.

## Precise responsive outer-scroll policy

```text
default width: 1200 px
minimum width: 1150 px
screen height > 1870 px: initial height = 1870 px
actual window height >= 1870 px: hide outer scrollbar and disable ordinary outer wheel routing
actual window height < 1870 px: show outer scrollbar and enable ordinary outer wheel routing
```

- Resets the outer Canvas to the top when the fixed high-window mode activates.
- Preserves the permanently visible Footer outside the scroll viewport.
- Preserves native scrolling priority for Run log, Recent jobs, Part status, Listbox and Combobox controls.
- Tests the exact 1869, 1870 and 1871 px boundaries.

## Unchanged core

The SQLite job-state engine, durable file writer, Resume, OCR, TTS and quiet-export paths remain unchanged.

## Historical evidence

The v2.3.1 Release Notes remain unchanged as historical evidence of the earlier 1900 px contract.
