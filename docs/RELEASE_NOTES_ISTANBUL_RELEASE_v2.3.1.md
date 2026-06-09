# Istanbul Release v2.3.1

This product-local desktop-shell patch keeps the v2.3.0 SQLite durable-state engine unchanged.

## Fixed shell

- Keeps the existing copyright and Constantinople signature Footer permanently visible.
- Moves only the internal workflow surface through the scroll viewport.
- Adds mouse-wheel and touchpad viewport scrolling.
- Preserves native scrolling for inner widgets such as Run log, Recent jobs, Part status and combobox controls.

## Deterministic geometry

```text
default width: 1200 px
minimum width: 1150 px
screen height > 1900 px: default height = 1900 px
smaller screens: safe visible clamp
```

## README cleanup

- Removes the outdated opening hero screenshot reference.
- Preserves historical screenshot assets below.
- Renames every historical section to `Historical interface`.

## Unchanged core

The SQLite job-state engine, durable file writer, TTS, OCR, Resume and quiet-export paths remain unchanged.
