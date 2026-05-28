"""PDF embedded-text extraction logic (PyMuPDF imported lazily)."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import (
    DEFAULT_CHUNK_TARGET_CHARS,
    EXTRACTION_STATUS_OCR_REQUIRED,
    EXTRACTION_STATUS_PARTIAL,
    EXTRACTION_STATUS_READY,
    MIN_PDF_MEANINGFUL_PAGE_CHARS,
    MIN_PDF_PAGE_TEXT_COVERAGE_RATIO,
    MIN_PDF_TOTAL_TEXT_CHARS,
    WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD,
)
from text_cleanup import normalize_text_block
from text_blocks import TextBlock, TextChunk, build_chunks_from_blocks


@dataclass(frozen=True)
class PdfPageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class PdfExtractionResult:
    status: str
    plain_text: str
    blocks: list[TextBlock]
    chunks: list[TextChunk]
    page_count: int
    detected_languages: list[str]
    warnings: list[str]


def extract_pdf_page_texts(raw: bytes) -> list[PdfPageText]:
    import fitz

    document = fitz.open(stream=raw, filetype="pdf")
    try:
        pages: list[PdfPageText] = []
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            text = (page.get_text("text") or "").strip()
            pages.append(PdfPageText(page_number=page_index + 1, text=text))
        return pages
    finally:
        document.close()


def assess_pdf_text_coverage(pages: list[PdfPageText]) -> tuple[bool, list[str]]:
    if not pages:
        return False, [WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD]

    total_chars = sum(len(page.text) for page in pages)
    meaningful_pages = sum(
        1 for page in pages if len(page.text) >= MIN_PDF_MEANINGFUL_PAGE_CHARS
    )
    coverage_ratio = meaningful_pages / len(pages)

    if total_chars < MIN_PDF_TOTAL_TEXT_CHARS:
        return False, [WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD]
    if coverage_ratio < MIN_PDF_PAGE_TEXT_COVERAGE_RATIO:
        return False, [WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD]
    return True, []


def build_pdf_extraction(
    raw: bytes,
    *,
    chunk_target_chars: int = DEFAULT_CHUNK_TARGET_CHARS,
) -> PdfExtractionResult:
    pages = extract_pdf_page_texts(raw)
    page_count = len(pages)
    coverage_ok, warnings = assess_pdf_text_coverage(pages)

    cleaned_page_texts = [
        normalize_text_block(page.text, repair_hyphenation=True, drop_page_numbers=True)
        for page in pages
    ]

    blocks: list[TextBlock] = []
    for index, (page, page_text) in enumerate(zip(pages, cleaned_page_texts), start=1):
        if not page_text:
            continue
        blocks.append(
            TextBlock(
                block_id=f"block-{index:06d}",
                block_type="paragraph",
                text=page_text,
                detected_language="unknown",
                source_page_number=page.page_number,
            )
        )

    if not blocks:
        return PdfExtractionResult(
            status=EXTRACTION_STATUS_OCR_REQUIRED,
            plain_text="",
            blocks=[],
            chunks=[],
            page_count=page_count,
            detected_languages=[],
            warnings=warnings,
        )

    plain_text = "\n\n".join(block.text for block in blocks)
    chunks = build_chunks_from_blocks(blocks, chunk_target_chars=chunk_target_chars)
    status = EXTRACTION_STATUS_READY if coverage_ok else EXTRACTION_STATUS_PARTIAL

    return PdfExtractionResult(
        status=status,
        plain_text=plain_text,
        blocks=blocks,
        chunks=chunks,
        page_count=page_count,
        detected_languages=[],
        warnings=[] if coverage_ok else warnings,
    )
