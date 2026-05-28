"""DOCX text extraction using Python stdlib ZIP + XML parsing."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from shared.contracts import DEFAULT_CHUNK_TARGET_CHARS, EXTRACTION_STRATEGY_DOCX
from text_cleanup import normalize_text_block
from text_blocks import TextBlock, TextChunk, build_chunks_from_blocks

DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass(frozen=True)
class DocxExtractionResult:
    plain_text: str
    blocks: list[TextBlock]
    chunks: list[TextChunk]
    detected_languages: list[str]
    table_count: int
    extraction_strategy: str = EXTRACTION_STRATEGY_DOCX


def _paragraph_style_is_heading(style_value: str | None) -> bool:
    if not style_value:
        return False
    normalized = style_value.lower()
    return "heading" in normalized or normalized.startswith("title")


def _extract_paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "t" and node.text:
            parts.append(node.text)
        elif tag == "tab":
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append("\n")
    return re.sub(r"\s+\n", "\n", "".join(parts)).strip()


def _extract_table_text(table: ET.Element) -> str:
    rows: list[str] = []
    for row in table.findall(".//w:tr", DOCX_NS):
        cells: list[str] = []
        for cell in row.findall(".//w:tc", DOCX_NS):
            cell_parts: list[str] = []
            for paragraph in cell.findall(".//w:p", DOCX_NS):
                paragraph_text = _extract_paragraph_text(paragraph)
                if paragraph_text:
                    cell_parts.append(paragraph_text)
            cells.append(" ".join(cell_parts).strip())
        if any(cell.strip() for cell in cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows).strip()


def build_docx_extraction(
    raw: bytes,
    *,
    chunk_target_chars: int = DEFAULT_CHUNK_TARGET_CHARS,
) -> DocxExtractionResult:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        document_xml = archive.read("word/document.xml")

    root = ET.fromstring(document_xml)
    body = root.find("w:body", DOCX_NS)
    if body is None:
        return DocxExtractionResult(
            plain_text="",
            blocks=[],
            chunks=[],
            detected_languages=[],
            table_count=0,
        )

    blocks: list[TextBlock] = []
    table_count = 0

    for child in body:
        local_name = child.tag.rsplit("}", 1)[-1]
        if local_name == "p":
            paragraph_text = normalize_text_block(_extract_paragraph_text(child))
            if not paragraph_text:
                continue
            style = child.find(".//w:pStyle", DOCX_NS)
            style_value = style.get(f"{{{DOCX_NS['w']}}}val") if style is not None else None
            block_type = (
                "heading"
                if _paragraph_style_is_heading(style_value)
                else "paragraph"
            )
            blocks.append(
                TextBlock(
                    block_id=f"block-{len(blocks) + 1:06d}",
                    block_type=block_type,
                    text=paragraph_text,
                )
            )
        elif local_name == "tbl":
            table_text = normalize_text_block(_extract_table_text(child))
            if not table_text:
                continue
            table_count += 1
            blocks.append(
                TextBlock(
                    block_id=f"block-{len(blocks) + 1:06d}",
                    block_type="table",
                    text=table_text,
                )
            )

    plain_text = "\n\n".join(block.text for block in blocks)
    chunks = build_chunks_from_blocks(blocks, chunk_target_chars=chunk_target_chars)

    return DocxExtractionResult(
        plain_text=plain_text,
        blocks=blocks,
        chunks=chunks,
        detected_languages=[],
        table_count=table_count,
    )
