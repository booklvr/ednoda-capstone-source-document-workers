"""Shared text block and chunk types for source-document extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.contracts import DEFAULT_CHUNK_TARGET_CHARS


@dataclass(frozen=True)
class TextBlock:
    block_id: str
    block_type: str
    text: str
    detected_language: str = "unknown"
    source_page_number: int | None = None


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    index: int
    char_start: int
    char_end: int
    source_block_ids: list[str]
    text: str


def build_chunks_from_blocks(
    blocks: list[TextBlock],
    *,
    chunk_target_chars: int = DEFAULT_CHUNK_TARGET_CHARS,
) -> list[TextChunk]:
    if not blocks:
        return []

    target = max(1, chunk_target_chars)
    chunks: list[TextChunk] = []
    current_block_ids: list[str] = []
    current_parts: list[str] = []
    current_length = 0
    char_cursor = 0

    def flush_chunk() -> None:
        nonlocal char_cursor, current_block_ids, current_parts, current_length
        if not current_parts:
            return
        chunk_text = "\n\n".join(current_parts)
        chunk_index = len(chunks)
        chunks.append(
            TextChunk(
                chunk_id=f"chunk-{chunk_index + 1:06d}",
                index=chunk_index,
                char_start=char_cursor,
                char_end=char_cursor + len(chunk_text),
                source_block_ids=list(dict.fromkeys(current_block_ids)),
                text=chunk_text,
            )
        )
        char_cursor += len(chunk_text) + 2
        current_block_ids = []
        current_parts = []
        current_length = 0

    for block in blocks:
        for part in _split_oversized_text(block.text, target):
            addition = len(part) + (2 if current_parts else 0)
            if current_parts and current_length + addition > target:
                flush_chunk()
            current_block_ids.append(block.block_id)
            current_parts.append(part)
            current_length += addition

    flush_chunk()
    return chunks


def _split_oversized_text(text: str, target: int) -> list[str]:
    if len(text) <= target:
        return [text]

    pieces: list[str] = []
    remaining = text.strip()
    while len(remaining) > target:
        split_at = _find_split_point(remaining, target)
        pieces.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        pieces.append(remaining)
    return [piece for piece in pieces if piece]


def _find_split_point(text: str, target: int) -> int:
    window = text[:target]
    candidates = [
        window.rfind("\n\n"),
        window.rfind("\n"),
        max((match.end() for match in re.finditer(r"[.!?]\s+", window)), default=-1),
        window.rfind(" "),
    ]
    split_at = max(candidates)
    if split_at >= max(1, target // 2):
        return split_at
    return target
