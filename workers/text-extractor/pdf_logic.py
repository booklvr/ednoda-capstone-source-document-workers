"""PDF embedded-text extraction with table + figure detection (pdfplumber).

Single-pass design: ``_parse_pdf_pages`` is the only function that opens the PDF.
It returns, per page, an ordered list of reading-order segments (paragraph text,
table markdown, image placeholders) so the resulting blocks and ``plain.txt``
preserve the visual layout. Detected figures (raster images + vector graphics)
are rasterized to PNG bytes so the package writer can save them alongside the
text and reference them from ``preview.md``.

``extract_pdf_page_texts`` is a thin, monkeypatchable hook used only as a
fallback when the real parse fails (unit tests pass synthetic bytes such as
``b"%PDF-1.4"`` and inject page text through this hook instead).
"""

from __future__ import annotations

import io
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


# Placeholder emitted in plain text / block text where an image or vector figure
# was detected. Blocks/plain.txt/chunks keep this clean marker; preview.md renders
# the matching ![image](...) reference from the block's saved PNG.
IMAGE_PLACEHOLDER = "[image]"

# A vector-graphic cluster smaller than this area (pt^2, ~20x20pt) is treated as a
# decorative flourish, not a figure.
_MIN_FIGURE_AREA = 400.0

# Vertical gap (pt) below which two structured boxes are merged into one.
_BAND_MERGE_GAP = 15.0

# Padding (pt) around a figure bbox when rasterizing, so strokes are not clipped.
_FIGURE_RENDER_PADDING = 3.0

# Rasterization resolution (DPI) for saved figure PNGs.
_FIGURE_RENDER_DPI = 150

# block_type values per segment kind (see source-document-text-package-contract).
_BLOCK_TYPE_BY_KIND = {"paragraph": "paragraph", "table": "table", "image": "image"}
_ID_LETTER_BY_KIND = {"paragraph": "p", "table": "t", "image": "i"}


@dataclass(frozen=True)
class PdfPageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractedImage:
    """A detected figure rendered to PNG, tied to its image block."""

    block_id: str
    page_number: int
    png_bytes: bytes


@dataclass(frozen=True)
class _Segment:
    """One reading-order piece of a page."""

    kind: str                       # "paragraph" | "table" | "image"
    text: str                       # paragraph text, table markdown, or placeholder
    image_bytes: bytes | None = None  # PNG bytes for image segments


# Rich per-page data from the single pdfplumber pass.
@dataclass(frozen=True)
class _PdfPageData:
    page_number: int
    text: str                  # full page text layer (for coverage assessment)
    segments: list[_Segment]   # ordered reading-order segments
    table_count: int
    image_count: int


@dataclass(frozen=True)
class PdfExtractionResult:
    status: str
    plain_text: str
    blocks: list[TextBlock]
    chunks: list[TextChunk]
    page_count: int
    detected_languages: list[str]
    warnings: list[str]
    table_count: int = 0
    image_count: int = 0
    images: list[ExtractedImage] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.images is None:
            object.__setattr__(self, "images", [])


def _table_to_markdown(table: list[list[str | None]]) -> str:
    if not table:
        return ""
    rows = [
        ["" if cell is None else str(cell).strip().replace("\n", " ") for cell in row]
        for row in table
    ]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return ""
    col_count = max(len(row) for row in rows)
    rows = [row + [""] * (col_count - len(row)) for row in rows]
    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join(["---"] * col_count) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join([header, separator, *body_lines])


def _merge_boxes(boxes: list[tuple[float, float, float, float]]) -> list[tuple[float, float, float, float]]:
    """Merge overlapping / near-adjacent bboxes (x0, top, x1, bottom) by vertical
    proximity, unioning their extents."""
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda b: b[1])
    merged: list[list[float]] = [list(ordered[0])]
    for x0, top, x1, bottom in ordered[1:]:
        current = merged[-1]
        if top <= current[3] + _BAND_MERGE_GAP:
            current[0] = min(current[0], x0)
            current[1] = min(current[1], top)
            current[2] = max(current[2], x1)
            current[3] = max(current[3], bottom)
        else:
            merged.append([x0, top, x1, bottom])
    return [(c[0], c[1], c[2], c[3]) for c in merged]


def _detect_figures(page, table_bands: list[tuple[float, float]]) -> list[tuple[float, float, float, float]]:
    """Detect image / vector-figure bboxes on a page.

    Two sources:
      - raster images via ``page.images`` (embedded bitmaps), and
      - vector graphics via ``page.curves`` (a strong figure signal — tables and
        rules use straight lines/rects, not bezier curves, so this avoids the
        false positives that bare rect/line clustering would cause).
    Boxes whose vertical center sits inside a detected table are dropped, as are
    sub-threshold specks. Remaining boxes are merged into reading-order figures.
    """
    width, height = float(page.width), float(page.height)

    def _clamp_v(value: float) -> float:
        return max(0.0, min(height, float(value)))

    def _clamp_h(value: float) -> float:
        return max(0.0, min(width, float(value)))

    def _inside_table(top: float, bottom: float) -> bool:
        center = (top + bottom) / 2
        return any(t_top <= center <= t_bottom for t_top, t_bottom in table_bands)

    raw: list[tuple[float, float, float, float]] = []
    for image in page.images:
        raw.append((_clamp_h(image["x0"]), _clamp_v(image["top"]), _clamp_h(image["x1"]), _clamp_v(image["bottom"])))
    for curve in page.curves:
        raw.append((_clamp_h(curve["x0"]), _clamp_v(curve["top"]), _clamp_h(curve["x1"]), _clamp_v(curve["bottom"])))

    figures: list[tuple[float, float, float, float]] = []
    for x0, top, x1, bottom in _merge_boxes(raw):
        if _inside_table(top, bottom):
            continue
        if (x1 - x0) * (bottom - top) < _MIN_FIGURE_AREA:
            continue
        figures.append((x0, top, x1, bottom))
    return figures


def _render_region_png(page, bbox: tuple[float, float, float, float]) -> bytes | None:
    """Rasterize a page region (with small padding) to PNG bytes.

    Works for both raster images and vector graphics since it snapshots pixels.
    Returns None if rendering is unavailable in the environment.
    """
    width, height = float(page.width), float(page.height)
    x0, top, x1, bottom = bbox
    padded = (
        max(0.0, x0 - _FIGURE_RENDER_PADDING),
        max(0.0, top - _FIGURE_RENDER_PADDING),
        min(width, x1 + _FIGURE_RENDER_PADDING),
        min(height, bottom + _FIGURE_RENDER_PADDING),
    )
    try:
        image = page.crop(padded).to_image(resolution=_FIGURE_RENDER_DPI)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return None


def _parse_single_page(page, page_number: int) -> _PdfPageData:
    width, height = float(page.width), float(page.height)
    full_text = (page.extract_text() or "").strip()

    tables = page.find_tables()
    table_bands = [(float(t.bbox[1]), float(t.bbox[3])) for t in tables]
    figures = _detect_figures(page, table_bands)

    # Structured regions (tables + figures) in reading order, each carrying its
    # rendered content. Text in the gaps between them becomes paragraph segments.
    regions: list[tuple[float, float, _Segment]] = []
    for table, (top, bottom) in zip(tables, table_bands):
        markdown = _table_to_markdown(table.extract())
        if markdown:
            regions.append((top, bottom, _Segment("table", markdown)))
    for bbox in figures:
        _x0, top, _x1, bottom = bbox
        png = _render_region_png(page, bbox)
        regions.append((top, bottom, _Segment("image", IMAGE_PLACEHOLDER, image_bytes=png)))
    regions.sort(key=lambda item: item[0])

    segments: list[_Segment] = []
    if not regions:
        if full_text:
            segments.append(_Segment("paragraph", full_text))
        return _PdfPageData(
            page_number=page_number,
            text=full_text,
            segments=segments,
            table_count=len(tables),
            image_count=len(figures),
        )

    prev_bottom = 0.0
    for top, bottom, region_segment in regions:
        if top > prev_bottom:
            gap_text = (page.crop((0, prev_bottom, width, top)).extract_text() or "").strip()
            if gap_text:
                segments.append(_Segment("paragraph", gap_text))
        segments.append(region_segment)
        prev_bottom = max(prev_bottom, bottom)
    if prev_bottom < height:
        tail_text = (page.crop((0, prev_bottom, width, height)).extract_text() or "").strip()
        if tail_text:
            segments.append(_Segment("paragraph", tail_text))

    return _PdfPageData(
        page_number=page_number,
        text=full_text,
        segments=segments,
        table_count=len(tables),
        image_count=len(figures),
    )


def _parse_pdf_pages(raw: bytes) -> list[_PdfPageData]:
    """Single pdfplumber pass: structured reading-order segments per page."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return [
            _parse_single_page(page, page_index + 1)
            for page_index, page in enumerate(pdf.pages)
        ]


def extract_pdf_page_texts(raw: bytes) -> list[PdfPageText]:
    """Public, monkeypatchable hook returning one PdfPageText per page.

    Used only as a fallback by build_pdf_extraction when the real pdfplumber
    parse fails — tests replace this at module level to inject controlled page
    text without a real PDF file.
    """
    return [
        PdfPageText(page_number=p.page_number, text=p.text)
        for p in _parse_pdf_pages(raw)
    ]


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


def _blocks_for_page(
    page_index: int, page_number: int, segments: list[_Segment]
) -> tuple[list[TextBlock], list[ExtractedImage]]:
    """Turn one page's reading-order segments into TextBlocks (+ ExtractedImages).

    A page with a single paragraph and no structured content keeps the plain
    ``block-NNNNNN`` id (the historical/contract shape exercised by unit tests).
    Pages with tables or figures get per-kind suffixed ids to stay unique.
    """
    cleaned: list[_Segment] = []
    for segment in segments:
        if segment.kind == "paragraph":
            text = normalize_text_block(segment.text, repair_hyphenation=True, drop_page_numbers=True)
            if text:
                cleaned.append(_Segment("paragraph", text))
        elif segment.text:
            cleaned.append(segment)

    if not cleaned:
        return [], []

    if len(cleaned) == 1 and cleaned[0].kind == "paragraph":
        block = TextBlock(
            block_id=f"block-{page_index:06d}",
            block_type="paragraph",
            text=cleaned[0].text,
            detected_language="unknown",
            source_page_number=page_number,
        )
        return [block], []

    blocks: list[TextBlock] = []
    images: list[ExtractedImage] = []
    counters: dict[str, int] = {}
    for segment in cleaned:
        counters[segment.kind] = counters.get(segment.kind, 0) + 1
        letter = _ID_LETTER_BY_KIND[segment.kind]
        block_id = f"block-{page_index:06d}-{letter}{counters[segment.kind]:03d}"
        blocks.append(
            TextBlock(
                block_id=block_id,
                block_type=_BLOCK_TYPE_BY_KIND[segment.kind],
                text=segment.text,
                detected_language="unknown",
                source_page_number=page_number,
            )
        )
        if segment.kind == "image" and segment.image_bytes is not None:
            images.append(ExtractedImage(block_id=block_id, page_number=page_number, png_bytes=segment.image_bytes))
    return blocks, images


def build_pdf_extraction(
    raw: bytes,
    *,
    chunk_target_chars: int = DEFAULT_CHUNK_TARGET_CHARS,
) -> PdfExtractionResult:
    # Single real parse. If it raises (tests pass synthetic bytes), fall back to
    # the monkeypatchable text-only hook — which the tests have replaced.
    try:
        rich_pages: list[_PdfPageData] | None = _parse_pdf_pages(raw)
    except Exception:
        rich_pages = None

    if rich_pages is not None:
        page_texts = [PdfPageText(p.page_number, p.text) for p in rich_pages]
    else:
        page_texts = extract_pdf_page_texts(raw)

    page_count = len(page_texts)
    coverage_ok, warnings = assess_pdf_text_coverage(page_texts)

    rich_by_number = {p.page_number: p for p in rich_pages} if rich_pages else {}
    table_count = sum(p.table_count for p in rich_by_number.values())
    image_count = sum(p.image_count for p in rich_by_number.values())

    blocks: list[TextBlock] = []
    images: list[ExtractedImage] = []
    for page_index, pt in enumerate(page_texts, start=1):
        rich = rich_by_number.get(pt.page_number)
        segments = rich.segments if rich is not None else (
            [_Segment("paragraph", pt.text)] if pt.text else []
        )
        page_blocks, page_images = _blocks_for_page(page_index, pt.page_number, segments)
        blocks.extend(page_blocks)
        images.extend(page_images)

    if not blocks:
        return PdfExtractionResult(
            status=EXTRACTION_STATUS_OCR_REQUIRED,
            plain_text="",
            blocks=[],
            chunks=[],
            page_count=page_count,
            detected_languages=[],
            warnings=warnings,
            table_count=0,
            image_count=0,
            images=[],
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
        table_count=table_count,
        image_count=image_count,
        images=images,
    )
