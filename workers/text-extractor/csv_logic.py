"""CSV text extraction for Full MVP Source Documents."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from itertools import zip_longest

from shared.contracts import DEFAULT_CHUNK_TARGET_CHARS, EXTRACTION_STRATEGY_CSV
from text_blocks import TextBlock, TextChunk, build_chunks_from_blocks


@dataclass(frozen=True)
class CsvExtractionResult:
    plain_text: str
    blocks: list[TextBlock]
    chunks: list[TextChunk]
    detected_languages: list[str]
    table_count: int
    extraction_strategy: str = EXTRACTION_STRATEGY_CSV


def decode_csv_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def build_csv_extraction(
    raw: bytes,
    *,
    chunk_target_chars: int = DEFAULT_CHUNK_TARGET_CHARS,
) -> CsvExtractionResult:
    text = decode_csv_bytes(raw)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    headers: list[str] = []
    data_rows: list[list[str]] = []
    if rows:
        headers = [cell.strip() for cell in rows[0]]
        data_rows = [[cell.strip() for cell in row] for row in rows[1:]]

    blocks: list[TextBlock] = []
    plain_lines: list[str] = []

    if headers:
        header_line = ", ".join(headers)
        blocks.append(
            TextBlock(
                block_id="block-000001",
                block_type="table_header",
                text=header_line,
            )
        )
        plain_lines.append(header_line)

    for index, row in enumerate(data_rows, start=1):
        row_text = _format_csv_row(headers, row)
        block_id = f"block-{index + 1:06d}"
        blocks.append(
            TextBlock(
                block_id=block_id,
                block_type="table_row",
                text=row_text,
            )
        )
        plain_lines.append(row_text)

    plain_text = "\n".join(plain_lines)
    chunks = build_chunks_from_blocks(blocks, chunk_target_chars=chunk_target_chars)
    return CsvExtractionResult(
        plain_text=plain_text,
        blocks=blocks,
        chunks=chunks,
        detected_languages=[],
        table_count=1 if blocks else 0,
    )


def _format_csv_row(headers: list[str], row: list[str]) -> str:
    if not headers:
        return ", ".join(row)
    parts: list[str] = []
    for index, (header, cell) in enumerate(zip_longest(headers, row, fillvalue=""), start=1):
        cell_text = str(cell).strip()
        if not cell_text:
            continue
        header_text = str(header).strip() or f"column_{index}"
        parts.append(f"{header_text}: {cell_text}")
    return " | ".join(parts)
