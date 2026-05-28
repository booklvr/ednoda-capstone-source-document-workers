"""Pure TXT extraction logic for Alpha text packages."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import DEFAULT_CHUNK_TARGET_CHARS
from text_cleanup import normalize_text_block
from text_blocks import TextBlock, TextChunk, build_chunks_from_blocks


@dataclass(frozen=True)
class TxtExtractionResult:
    plain_text: str
    blocks: list[TextBlock]
    chunks: list[TextChunk]
    detected_languages: list[str]


def decode_text_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def split_paragraph_blocks(text: str) -> list[str]:
    normalized = normalize_text_block(text, repair_hyphenation=False)
    if not normalized:
        return []
    if "\n\n" not in normalized:
        return [line.strip() for line in normalized.split("\n") if line.strip()]
    parts = [part.strip() for part in normalized.split("\n\n") if part.strip()]
    return parts


def build_txt_extraction(
    raw: bytes,
    *,
    chunk_target_chars: int = DEFAULT_CHUNK_TARGET_CHARS,
) -> TxtExtractionResult:
    decoded = decode_text_bytes(raw)
    paragraphs = split_paragraph_blocks(decoded)
    blocks: list[TextBlock] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        block_id = f"block-{index:06d}"
        blocks.append(
            TextBlock(
                block_id=block_id,
                block_type="paragraph",
                text=paragraph,
                detected_language="unknown",
            )
        )

    plain_text = "\n\n".join(block.text for block in blocks)
    chunks = build_chunks_from_blocks(blocks, chunk_target_chars=chunk_target_chars)
    return TxtExtractionResult(
        plain_text=plain_text,
        blocks=blocks,
        chunks=chunks,
        detected_languages=[],
    )
