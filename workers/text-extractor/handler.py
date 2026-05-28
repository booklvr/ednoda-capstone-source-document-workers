"""Source Document text extraction worker."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

WORKER_ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTRACTOR_DIR = Path(__file__).resolve().parent
for path in (WORKER_ROOT, TEXT_EXTRACTOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared.callback_post import build_extraction_callback_body, try_post_extraction_callback
from shared.contracts import EXTRACTION_STATUS_FAILED, EXTRACTION_STATUS_OCR_REQUIRED
from shared.event import TextExtractorEvent, WorkerEventError, parse_text_extractor_event
from shared.file_sniff import validate_source_document_file_content
from shared.file_types import (
    is_csv_file,
    is_docx_file,
    is_pdf_file,
    is_pptx_file,
    is_txt_file,
)
from shared.keys import build_extraction_text_package_keys
from shared.limits import (
    ProcessingDeadline,
    resolve_max_blocks,
    resolve_max_chunks,
    resolve_max_extraction_chars,
    resolve_max_processing_seconds,
)
from shared.s3_client import create_boto3_s3_client, read_object_bytes
from shared.worker_errors import is_transient_infrastructure_error
from csv_logic import build_csv_extraction
from docx_logic import build_docx_extraction
from extraction_limits import apply_extraction_limits
from package_writer import (
    build_extraction_branch_result,
    build_ocr_required_result,
    package_from_csv_result,
    package_from_docx_result,
    package_from_pdf_result,
    package_from_pptx_result,
    package_from_txt_result,
    write_text_package,
)
from pdf_logic import build_pdf_extraction
from pptx_logic import build_pptx_extraction
from txt_logic import build_txt_extraction


def resolve_text_bucket(event: TextExtractorEvent) -> str:
    return event.text_bucket or __import__("os").environ.get("SOURCE_DOCUMENT_TEXT_BUCKET", "")


def _finalize_extracted_package(extracted: dict[str, Any]) -> dict[str, Any]:
    limited = apply_extraction_limits(
        plain_text=extracted["plain_text"],
        blocks=extracted["blocks"],
        chunks=extracted["chunks"],
        max_chars=resolve_max_extraction_chars(),
        max_blocks=resolve_max_blocks(),
        max_chunks=resolve_max_chunks(),
    )
    warnings = [*extracted.get("warnings", []), *limited.warnings]
    status = extracted["status"]
    if limited.status != "ready" and status == "ready":
        status = limited.status

    return {
        **extracted,
        "status": status,
        "plain_text": limited.plain_text,
        "blocks": limited.blocks,
        "chunks": limited.chunks,
        "warnings": warnings,
    }


def process_text_extraction(
    event: TextExtractorEvent,
    *,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    deadline = ProcessingDeadline(resolve_max_processing_seconds())

    text_bucket = resolve_text_bucket(event)
    if not text_bucket:
        return build_extraction_branch_result(
            status=EXTRACTION_STATUS_FAILED,
            text_bucket=None,
            package_keys=None,
            plain_text="",
            blocks=[],
            chunks=[],
            page_count=None,
            warnings=[],
            error={
                "code": "text_bucket_missing",
                "message": "textBucket is required on the event or SOURCE_DOCUMENT_TEXT_BUCKET env var.",
            },
        )

    client = s3_client or create_boto3_s3_client()
    raw = read_object_bytes(
        client,
        bucket=event.original.bucket,
        key=event.original.key,
    )

    sniff = validate_source_document_file_content(
        raw,
        file_extension=event.original.file_extension,
        mime_type=event.original.mime_type,
    )
    if not sniff.valid:
        return build_extraction_branch_result(
            status=EXTRACTION_STATUS_FAILED,
            text_bucket=None,
            package_keys=None,
            plain_text="",
            blocks=[],
            chunks=[],
            page_count=None,
            warnings=[],
            error={
                "code": sniff.error_code or "signature_mismatch",
                "message": sniff.message or "Uploaded file content does not match declared type.",
            },
        )

    file_extension = event.original.file_extension
    mime_type = event.original.mime_type

    if deadline.exceeded():
        return build_extraction_branch_result(
            status=EXTRACTION_STATUS_FAILED,
            text_bucket=None,
            package_keys=None,
            plain_text="",
            blocks=[],
            chunks=[],
            page_count=None,
            warnings=[],
            error={
                "code": "processing_timeout",
                "message": "Text extraction exceeded MAX_PROCESSING_SECONDS.",
            },
        )

    if is_txt_file(file_extension, mime_type):
        extracted = package_from_txt_result(build_txt_extraction(raw))
    elif is_pdf_file(file_extension, mime_type):
        extracted = package_from_pdf_result(build_pdf_extraction(raw))
    elif is_csv_file(file_extension, mime_type):
        extracted = package_from_csv_result(build_csv_extraction(raw))
    elif is_docx_file(file_extension, mime_type):
        extracted = package_from_docx_result(build_docx_extraction(raw))
    elif is_pptx_file(file_extension, mime_type):
        extracted = package_from_pptx_result(build_pptx_extraction(raw))
    else:
        return build_extraction_branch_result(
            status=EXTRACTION_STATUS_FAILED,
            text_bucket=None,
            package_keys=None,
            plain_text="",
            blocks=[],
            chunks=[],
            page_count=None,
            warnings=[],
            error={
                "code": "unsupported_file_type",
                "message": f"Text extractor does not support file type ({file_extension}).",
            },
        )

    if extracted["status"] == EXTRACTION_STATUS_OCR_REQUIRED:
        return build_ocr_required_result(
            page_count=extracted["page_count"],
            warnings=extracted["warnings"],
        )

    extracted = _finalize_extracted_package(extracted)

    package_keys = build_extraction_text_package_keys(
        text_bucket,
        event.owner_user_id,
        event.source_document_id,
        event.extraction_id,
    )

    write_text_package(
        client,
        text_bucket=text_bucket,
        package_keys=package_keys,
        source_document_id=event.source_document_id,
        extraction_id=event.extraction_id,
        original_filename=event.original_filename,
        original_mime_type=mime_type,
        file_extension=file_extension,
        original_bucket=event.original.bucket,
        original_key=event.original.key,
        extraction_strategy=extracted["extraction_strategy"],
        status=extracted["status"],
        plain_text=extracted["plain_text"],
        blocks=extracted["blocks"],
        chunks=extracted["chunks"],
        page_count=extracted["page_count"],
        detected_languages=extracted["detected_languages"],
        warnings=extracted["warnings"],
    )

    return build_extraction_branch_result(
        status=extracted["status"],
        text_bucket=text_bucket,
        package_keys=package_keys,
        plain_text=extracted["plain_text"],
        blocks=extracted["blocks"],
        chunks=extracted["chunks"],
        page_count=extracted["page_count"],
        slide_count=extracted.get("slide_count"),
        table_count=extracted.get("table_count"),
        warnings=extracted["warnings"],
    )


def handler(event: dict[str, Any], _context: Any | None = None) -> dict[str, Any]:
    try:
        parsed = parse_text_extractor_event(event)
    except WorkerEventError as error:
        return build_extraction_branch_result(
            status=EXTRACTION_STATUS_FAILED,
            text_bucket=None,
            package_keys=None,
            plain_text="",
            blocks=[],
            chunks=[],
            page_count=None,
            warnings=[],
            error={"code": "invalid_event", "message": str(error)},
        )

    try:
        result = process_text_extraction(parsed)
    except Exception as error:
        if is_transient_infrastructure_error(error):
            raise
        result = build_extraction_branch_result(
            status=EXTRACTION_STATUS_FAILED,
            text_bucket=None,
            package_keys=None,
            plain_text="",
            blocks=[],
            chunks=[],
            page_count=None,
            warnings=[],
            error={
                "code": "text_extraction_failed",
                "message": str(error),
            },
        )

    callback_body = build_extraction_callback_body(parsed, result)
    try_post_extraction_callback(callback_body)
    return result
