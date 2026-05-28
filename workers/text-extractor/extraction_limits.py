"""Apply Full MVP extraction limits with partial-result warnings."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import (
    EXTRACTION_STATUS_PARTIAL,
    EXTRACTION_STATUS_READY,
    WARNING_EXTRACTION_BLOCKS_TRUNCATED,
    WARNING_EXTRACTION_CHARS_TRUNCATED,
    WARNING_EXTRACTION_CHUNKS_TRUNCATED,
)
from text_blocks import TextBlock, TextChunk, build_chunks_from_blocks


@dataclass(frozen=True)
class LimitedExtraction:
    status: str
    plain_text: str
    blocks: list[TextBlock]
    chunks: list[TextChunk]
    warnings: list[str]


def apply_extraction_limits(
    *,
    plain_text: str,
    blocks: list[TextBlock],
    chunks: list[TextChunk],
    max_chars: int,
    max_blocks: int,
    max_chunks: int,
) -> LimitedExtraction:
    warnings: list[str] = []
    limited_blocks = blocks
    limited_chunks = chunks
    limited_text = plain_text
    status = EXTRACTION_STATUS_READY

    if len(limited_blocks) > max_blocks:
        limited_blocks = limited_blocks[:max_blocks]
        limited_text = "\n\n".join(block.text for block in limited_blocks)
        limited_chunks = build_chunks_from_blocks(limited_blocks)
        warnings.append(WARNING_EXTRACTION_BLOCKS_TRUNCATED)
        status = EXTRACTION_STATUS_PARTIAL

    if len(limited_text) > max_chars:
        limited_text = limited_text[:max_chars]
        warnings.append(WARNING_EXTRACTION_CHARS_TRUNCATED)
        status = EXTRACTION_STATUS_PARTIAL

    if len(limited_chunks) > max_chunks:
        limited_chunks = limited_chunks[:max_chunks]
        warnings.append(WARNING_EXTRACTION_CHUNKS_TRUNCATED)
        status = EXTRACTION_STATUS_PARTIAL

    return LimitedExtraction(
        status=status,
        plain_text=limited_text,
        blocks=limited_blocks,
        chunks=limited_chunks,
        warnings=warnings,
    )
