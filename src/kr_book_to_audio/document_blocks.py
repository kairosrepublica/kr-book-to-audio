from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class DocumentBlock:
    """Semantic text block emitted by a format-specific extractor.

    The text engine should prefer these blocks over reconstructing structure
    from one lossy plain-text string.  ``type`` is intentionally small and
    product-oriented: it describes how the block should be treated for reading
    and TTS, not every possible source-format detail.
    """

    type: str
    text: str
    page: int | None = None
    level: int | None = None
    confidence: float = 1.0
    source: str = "unknown"

    def normalized(self) -> "DocumentBlock":
        text = "\n".join(line.strip() for line in self.text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()
        return DocumentBlock(
            type=self.type,
            text=text,
            page=self.page,
            level=self.level,
            confidence=self.confidence,
            source=self.source,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_blocks(blocks: Iterable[DocumentBlock]) -> list[DocumentBlock]:
    normalized: list[DocumentBlock] = []
    previous: tuple[str, str, int | None] | None = None
    for block in blocks:
        item = block.normalized()
        if not item.text:
            continue
        key = (item.type, item.text, item.page)
        if key == previous:
            continue
        normalized.append(item)
        previous = key
    return normalized


def blocks_to_raw_text(blocks: Iterable[DocumentBlock]) -> str:
    """Render blocks as reviewable text while preserving semantic boundaries."""
    return "\n\n".join(block.text.strip() for block in normalize_blocks(blocks) if block.text.strip())
