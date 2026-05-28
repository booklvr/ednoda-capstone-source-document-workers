"""Build and write candidate-type-free Alpha text packages to S3.

Output: manifest.json, plain.txt, blocks/*.json, chunks/*.json only.
Semantic candidate labels (vocab/expression/question/unknown) are assigned later
by candidate extraction (stub or UBC), not by this worker.
"""

from __future__ import annotations

import json
from typing import Any

from shared.contracts import (
    BLOCK_VERSION,
    EXTRACTION_STRATEGY_PDF_TEXT_LAYER,
    EXTRACTION_STRATEGY_PLAIN_TEXT,
    EXTRACTION_STATUS_OCR_REQUIRED,
    EXTRACTION_STATUS_READY,
    MANIFEST_VERSION,
)
from shared.keys import format_block_key, format_chunk_key
from shared.s3_client import S3Client, write_object_bytes
from pdf_logic import PdfExtractionResult
from text_blocks import TextBlock, TextChunk
from txt_logic import TxtExtractionResult


def is_txt_file(file_extension: str, mime_type: str) -> bool:
    normalized = file_extension.lower()
    return normalized == ".txt" or mime_type == "text/plain"


def is_pdf_file(file_extension: str, mime_type: str) -> bool:
    normalized = file_extension.lower()
    return normalized == ".pdf" or mime_type == "application/pdf"


def build_block_payload(
    *,
    source_document_id: int,
    extraction_id: int,
    block: TextBlock,
) -> dict[str, Any]:
    source: dict[str, int] = {}
    if block.source_page_number is not None:
        source["pageNumber"] = block.source_page_number
    payload: dict[str, Any] = {
        "version": BLOCK_VERSION,
        "sourceDocumentId": source_document_id,
        "extractionId": extraction_id,
        "blockId": block.block_id,
        "source": source,
        "blockType": block.block_type,
        "text": block.text,
        "detectedLanguage": block.detected_language,
    }
    return payload


def build_chunk_payload(
    *,
    source_document_id: int,
    extraction_id: int,
    chunk: TextChunk,
) -> dict[str, Any]:
    return {
        "version": BLOCK_VERSION,
        "sourceDocumentId": source_document_id,
        "extractionId": extraction_id,
        "chunkId": chunk.chunk_id,
        "index": chunk.index,
        "charStart": chunk.char_start,
        "charEnd": chunk.char_end,
        "sourceBlockIds": chunk.source_block_ids,
        "text": chunk.text,
    }


def build_manifest(
    *,
    source_document_id: int,
    extraction_id: int,
    original_filename: str,
    original_mime_type: str,
    file_extension: str,
    original_bucket: str,
    original_key: str,
    text_bucket: str,
    package_keys: dict[str, str],
    extraction_strategy: str,
    status: str,
    plain_text: str,
    blocks: list[TextBlock],
    chunks: list[TextChunk],
    page_count: int | None,
    detected_languages: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    block_index = []
    for block_number, block in enumerate(blocks, start=1):
        block_key = format_block_key(package_keys["blocksPrefix"], block_number)
        item: dict[str, Any] = {
            "blockId": block.block_id,
            "bucket": text_bucket,
            "key": block_key,
            "blockType": block.block_type,
            "charCount": len(block.text),
            "detectedLanguage": block.detected_language,
        }
        if block.source_page_number is not None:
            item["sourcePageNumber"] = block.source_page_number
        block_index.append(item)

    chunk_items = []
    for chunk_number, chunk in enumerate(chunks, start=1):
        chunk_items.append(
            {
                "chunkId": chunk.chunk_id,
                "bucket": text_bucket,
                "key": format_chunk_key(package_keys["chunksPrefix"], chunk_number),
                "index": chunk.index,
                "charStart": chunk.char_start,
                "charEnd": chunk.char_end,
                "sourceBlockIds": chunk.source_block_ids,
            }
        )

    extraction_section: dict[str, Any] = {
        "status": status,
        "extractionStrategy": extraction_strategy,
        "charCount": len(plain_text),
        "blockCount": len(blocks),
        "chunkCount": len(chunks),
        "detectedLanguages": detected_languages,
        "warnings": warnings,
    }
    if page_count is not None:
        extraction_section["pageCount"] = page_count

    return {
        "version": MANIFEST_VERSION,
        "document": {
            "sourceDocumentId": source_document_id,
            "extractionId": extraction_id,
            "originalFilename": original_filename,
            "originalMimeType": original_mime_type,
            "fileExtension": file_extension,
            "originalBucket": original_bucket,
            "originalKey": original_key,
        },
        "extraction": extraction_section,
        "outputs": {
            "plainText": {
                "bucket": text_bucket,
                "key": package_keys["plainTextKey"],
            },
            "blockIndex": block_index,
            "chunks": chunk_items,
        },
    }


def write_text_package(
    client: S3Client,
    *,
    text_bucket: str,
    package_keys: dict[str, str],
    source_document_id: int,
    extraction_id: int,
    original_filename: str,
    original_mime_type: str,
    file_extension: str,
    original_bucket: str,
    original_key: str,
    extraction_strategy: str,
    status: str,
    plain_text: str,
    blocks: list[TextBlock],
    chunks: list[TextChunk],
    page_count: int | None,
    detected_languages: list[str],
    warnings: list[str],
) -> None:
    write_object_bytes(
        client,
        bucket=text_bucket,
        key=package_keys["plainTextKey"],
        body=plain_text.encode("utf-8"),
        content_type="text/plain; charset=utf-8",
    )

    for block_number, block in enumerate(blocks, start=1):
        block_key = format_block_key(package_keys["blocksPrefix"], block_number)
        payload = build_block_payload(
            source_document_id=source_document_id,
            extraction_id=extraction_id,
            block=block,
        )
        write_object_bytes(
            client,
            bucket=text_bucket,
            key=block_key,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )

    for chunk_number, chunk in enumerate(chunks, start=1):
        chunk_key = format_chunk_key(package_keys["chunksPrefix"], chunk_number)
        payload = build_chunk_payload(
            source_document_id=source_document_id,
            extraction_id=extraction_id,
            chunk=chunk,
        )
        write_object_bytes(
            client,
            bucket=text_bucket,
            key=chunk_key,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )

    manifest = build_manifest(
        source_document_id=source_document_id,
        extraction_id=extraction_id,
        original_filename=original_filename,
        original_mime_type=original_mime_type,
        file_extension=file_extension,
        original_bucket=original_bucket,
        original_key=original_key,
        text_bucket=text_bucket,
        package_keys=package_keys,
        extraction_strategy=extraction_strategy,
        status=status,
        plain_text=plain_text,
        blocks=blocks,
        chunks=chunks,
        page_count=page_count,
        detected_languages=detected_languages,
        warnings=warnings,
    )
    write_object_bytes(
        client,
        bucket=text_bucket,
        key=package_keys["manifestKey"],
        body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
    )


def package_from_txt_result(result: TxtExtractionResult) -> dict[str, Any]:
    return {
        "status": EXTRACTION_STATUS_READY,
        "plain_text": result.plain_text,
        "blocks": result.blocks,
        "chunks": result.chunks,
        "page_count": None,
        "slide_count": None,
        "table_count": None,
        "detected_languages": result.detected_languages,
        "warnings": [],
        "extraction_strategy": EXTRACTION_STRATEGY_PLAIN_TEXT,
    }


def package_from_pdf_result(result: PdfExtractionResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "plain_text": result.plain_text,
        "blocks": result.blocks,
        "chunks": result.chunks,
        "page_count": result.page_count,
        "slide_count": None,
        "table_count": None,
        "detected_languages": result.detected_languages,
        "warnings": result.warnings,
        "extraction_strategy": EXTRACTION_STRATEGY_PDF_TEXT_LAYER,
    }


def package_from_csv_result(result) -> dict[str, Any]:
    from shared.contracts import EXTRACTION_STRATEGY_CSV

    return {
        "status": EXTRACTION_STATUS_READY,
        "plain_text": result.plain_text,
        "blocks": result.blocks,
        "chunks": result.chunks,
        "page_count": None,
        "slide_count": None,
        "table_count": result.table_count,
        "detected_languages": result.detected_languages,
        "warnings": [],
        "extraction_strategy": EXTRACTION_STRATEGY_CSV,
    }


def package_from_docx_result(result) -> dict[str, Any]:
    from shared.contracts import EXTRACTION_STRATEGY_DOCX

    return {
        "status": EXTRACTION_STATUS_READY,
        "plain_text": result.plain_text,
        "blocks": result.blocks,
        "chunks": result.chunks,
        "page_count": None,
        "slide_count": None,
        "table_count": result.table_count,
        "detected_languages": result.detected_languages,
        "warnings": [],
        "extraction_strategy": EXTRACTION_STRATEGY_DOCX,
    }


def package_from_pptx_result(result) -> dict[str, Any]:
    from shared.contracts import EXTRACTION_STRATEGY_PPTX

    return {
        "status": EXTRACTION_STATUS_READY,
        "plain_text": result.plain_text,
        "blocks": result.blocks,
        "chunks": result.chunks,
        "page_count": None,
        "slide_count": result.slide_count,
        "table_count": result.table_count,
        "detected_languages": result.detected_languages,
        "warnings": [],
        "extraction_strategy": EXTRACTION_STRATEGY_PPTX,
    }


def build_extraction_branch_result(
    *,
    status: str,
    text_bucket: str | None,
    package_keys: dict[str, str] | None,
    plain_text: str,
    blocks: list[TextBlock],
    chunks: list[TextChunk],
    page_count: int | None,
    slide_count: int | None = None,
    table_count: int | None = None,
    warnings: list[str],
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    from shared.contracts import EXTRACTION_STATUS_PARTIAL, EXTRACTION_STATUS_READY

    text_available = status in {EXTRACTION_STATUS_READY, EXTRACTION_STATUS_PARTIAL}
    result: dict[str, Any] = {
        "status": status,
        "branch": "extraction",
        "textAvailable": text_available,
        "charCount": len(plain_text),
        "blockCount": len(blocks),
        "chunkCount": len(chunks),
    }
    if text_available and package_keys is not None and text_bucket is not None:
        result["textBucket"] = text_bucket
        result["manifestKey"] = package_keys["manifestKey"]
        result["plainTextKey"] = package_keys["plainTextKey"]
    if page_count is not None:
        result["pageCount"] = page_count
    if slide_count is not None:
        result["slideCount"] = slide_count
    if table_count is not None:
        result["tableCount"] = table_count
    if warnings:
        result["warnings"] = warnings
    if error:
        result["error"] = error
    return result


def build_ocr_required_result(
    *,
    page_count: int | None,
    warnings: list[str],
) -> dict[str, Any]:
    return build_extraction_branch_result(
        status=EXTRACTION_STATUS_OCR_REQUIRED,
        text_bucket=None,
        package_keys=None,
        plain_text="",
        blocks=[],
        chunks=[],
        page_count=page_count,
        warnings=warnings,
    )
