"""Signed Ednoda Source Document callback posting for Python workers."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from shared.contracts import (
    EXTRACTION_STRATEGY_CSV,
    EXTRACTION_STRATEGY_DOCX,
    EXTRACTION_STRATEGY_PDF_TEXT_LAYER,
    EXTRACTION_STRATEGY_PLAIN_TEXT,
    EXTRACTION_STRATEGY_PPTX,
    PREVIEW_STRATEGY_CSV_TABLE,
    PREVIEW_STRATEGY_PAGE_IMAGES,
    PREVIEW_STRATEGY_PLAIN_TEXT,
    PREVIEW_STRATEGY_UNSUPPORTED,
)
from shared.contracts import CANDIDATE_EXTRACTION_RESULT_VERSION
from shared.event import (
    CandidateExtractorEvent,
    PreviewGeneratorEvent,
    TextExtractorEvent,
)
from shared.ubc_input import UbcCandidateExtractionInputV1
from shared.file_types import (
    is_csv_file,
    is_docx_file,
    is_pdf_file,
    is_pptx_file,
    is_txt_file,
)

PREVIEW_CALLBACK_PATH = "/api/source-documents/preview/callback"
EXTRACTION_CALLBACK_PATH = "/api/source-documents/extraction/callback"
NODE_CANDIDATES_CALLBACK_PATH = "/api/source-documents/node-candidates/callback"

CALLBACK_HTTP_TIMEOUT_SECONDS = 30.0
SOURCE_DOCUMENT_WORKER_USER_AGENT = "EdnodaSourceDocumentWorker/1.0"


def iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sign_callback_body(secret: str, raw_body: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        raw_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def serialize_callback_body(body: dict[str, Any]) -> str:
    return json.dumps(body, separators=(",", ":"), sort_keys=True)


def build_signed_callback_headers(secret: str, raw_body: str) -> dict[str, str]:
    signature = sign_callback_body(secret, raw_body)
    return {
        "Content-Type": "application/json",
        "X-Ednoda-Signature": signature,
        "User-Agent": SOURCE_DOCUMENT_WORKER_USER_AGENT,
    }


def post_signed_source_document_callback(
    callback_url: str,
    body: dict[str, Any],
    *,
    error_label: str,
) -> None:
    secret = os.environ.get("SOURCE_DOCUMENT_CALLBACK_SECRET", "").strip()
    if not callback_url or not secret:
        return

    raw_body = serialize_callback_body(body)
    headers = build_signed_callback_headers(secret, raw_body)

    try:
        response = httpx.post(
            callback_url,
            content=raw_body,
            headers=headers,
            timeout=CALLBACK_HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as error:
        raise RuntimeError(
            f"{error_label} transport error: {error}",
        ) from error

    if response.status_code >= 400:
        raise RuntimeError(
            f"{error_label} failed ({response.status_code}): {response.text}",
        )


def preview_strategy_for_file(file_extension: str, mime_type: str) -> str:
    if is_txt_file(file_extension, mime_type):
        return PREVIEW_STRATEGY_PLAIN_TEXT
    if (
        is_pdf_file(file_extension, mime_type)
        or is_docx_file(file_extension, mime_type)
        or is_pptx_file(file_extension, mime_type)
    ):
        return PREVIEW_STRATEGY_PAGE_IMAGES
    if is_csv_file(file_extension, mime_type):
        return PREVIEW_STRATEGY_CSV_TABLE
    return PREVIEW_STRATEGY_UNSUPPORTED


def build_preview_callback_body(
    event: PreviewGeneratorEvent,
    result: dict[str, Any],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "sourceDocumentId": event.source_document_id,
        "attemptNumber": event.attempt_number,
        "occurredAtIso": iso_timestamp(),
        "previewId": event.preview_id,
        "status": result["status"],
        "previewStrategy": preview_strategy_for_file(
            event.original.file_extension,
            event.original.mime_type,
        ),
    }

    if event.workflow_execution_arn:
        body["workflowExecutionArn"] = event.workflow_execution_arn
    if event.workflow_execution_row_id is not None:
        body["workflowExecutionRowId"] = event.workflow_execution_row_id

    preview_bucket = result.get("previewBucket")
    if isinstance(preview_bucket, str) and preview_bucket:
        body["previewBucket"] = preview_bucket

    preview_prefix = result.get("previewPrefix")
    if isinstance(preview_prefix, str) and preview_prefix:
        body["previewPrefix"] = preview_prefix

    page_count = result.get("pageCount")
    if isinstance(page_count, int):
        body["pageCount"] = page_count

    pages = result.get("pages")
    if isinstance(pages, list) and pages:
        body["pages"] = pages

    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        body["warnings"] = warnings

    error = result.get("error")
    if isinstance(error, dict) and error:
        body["error"] = error

    return body


def resolve_preview_callback_url() -> str | None:
    explicit_url = os.environ.get("SOURCE_DOCUMENT_PREVIEW_CALLBACK_URL", "").strip()
    if explicit_url:
        return explicit_url
    ednoda_preview_url = os.environ.get("EDNODA_PREVIEW_CALLBACK_URL", "").strip()
    if ednoda_preview_url:
        return ednoda_preview_url

    base_url = os.environ.get("EDNODA_CALLBACK_BASE_URL", "").strip()
    if not base_url:
        return None

    return f"{base_url.rstrip('/')}{PREVIEW_CALLBACK_PATH}"


def post_preview_callback(body: dict[str, Any]) -> None:
    callback_url = resolve_preview_callback_url()
    if not callback_url:
        return

    post_signed_source_document_callback(
        callback_url,
        body,
        error_label="Source document preview callback",
    )


def try_post_preview_callback(body: dict[str, Any]) -> None:
    callback_url = resolve_preview_callback_url()
    secret = os.environ.get("SOURCE_DOCUMENT_CALLBACK_SECRET", "").strip()
    if not callback_url or not secret:
        return
    post_preview_callback(body)


def extraction_strategy_for_file(file_extension: str, mime_type: str) -> str:
    if is_txt_file(file_extension, mime_type):
        return EXTRACTION_STRATEGY_PLAIN_TEXT
    if is_pdf_file(file_extension, mime_type):
        return EXTRACTION_STRATEGY_PDF_TEXT_LAYER
    if is_csv_file(file_extension, mime_type):
        return EXTRACTION_STRATEGY_CSV
    if is_docx_file(file_extension, mime_type):
        return EXTRACTION_STRATEGY_DOCX
    if is_pptx_file(file_extension, mime_type):
        return EXTRACTION_STRATEGY_PPTX
    return "unsupported"


def build_extraction_callback_body(
    event: TextExtractorEvent,
    result: dict[str, Any],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "sourceDocumentId": event.source_document_id,
        "attemptNumber": event.attempt_number,
        "occurredAtIso": iso_timestamp(),
        "extractionId": event.extraction_id,
        "status": result["status"],
        "extractionStrategy": extraction_strategy_for_file(
            event.original.file_extension,
            event.original.mime_type,
        ),
    }

    if event.workflow_execution_arn:
        body["workflowExecutionArn"] = event.workflow_execution_arn
    if event.workflow_execution_row_id is not None:
        body["workflowExecutionRowId"] = event.workflow_execution_row_id

    text_bucket = result.get("textBucket")
    if isinstance(text_bucket, str) and text_bucket:
        body["textBucket"] = text_bucket

    manifest_key = result.get("manifestKey")
    if isinstance(manifest_key, str) and manifest_key:
        body["manifestKey"] = manifest_key

    plain_text_key = result.get("plainTextKey")
    if isinstance(plain_text_key, str) and plain_text_key:
        body["plainTextKey"] = plain_text_key

    for count_field in (
        "charCount",
        "blockCount",
        "chunkCount",
        "pageCount",
        "slideCount",
        "tableCount",
    ):
        count_value = result.get(count_field)
        if isinstance(count_value, int):
            body[count_field] = count_value

    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        body["warnings"] = warnings

    error = result.get("error")
    if isinstance(error, dict) and error:
        body["error"] = error

    return body


def resolve_extraction_callback_url() -> str | None:
    explicit_url = os.environ.get("SOURCE_DOCUMENT_EXTRACTION_CALLBACK_URL", "").strip()
    if explicit_url:
        return explicit_url

    base_url = os.environ.get("EDNODA_CALLBACK_BASE_URL", "").strip()
    if not base_url:
        return None

    return f"{base_url.rstrip('/')}{EXTRACTION_CALLBACK_PATH}"


def post_extraction_callback(body: dict[str, Any]) -> None:
    callback_url = resolve_extraction_callback_url()
    if not callback_url:
        return

    post_signed_source_document_callback(
        callback_url,
        body,
        error_label="Source document extraction callback",
    )


def try_post_extraction_callback(body: dict[str, Any]) -> None:
    callback_url = resolve_extraction_callback_url()
    secret = os.environ.get("SOURCE_DOCUMENT_CALLBACK_SECRET", "").strip()
    if not callback_url or not secret:
        return
    post_extraction_callback(body)


def build_node_candidates_callback_body(
    event: CandidateExtractorEvent,
    result: dict[str, Any],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "version": CANDIDATE_EXTRACTION_RESULT_VERSION,
        "sourceDocumentId": event.source_document_id,
        "extractionId": event.extraction_id,
        "attemptNumber": event.attempt_number,
        "occurredAtIso": iso_timestamp(),
        "status": result["status"],
        "candidates": result.get("candidates") or [],
    }

    if event.workflow_execution_arn:
        body["workflowExecutionArn"] = event.workflow_execution_arn
    if event.workflow_execution_row_id is not None:
        body["workflowExecutionRowId"] = event.workflow_execution_row_id
    if event.task_token:
        body["taskToken"] = event.task_token

    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        body["warnings"] = warnings

    error = result.get("error")
    if isinstance(error, dict) and error:
        body["error"] = error

    return body


def resolve_node_candidates_callback_url() -> str | None:
    explicit_url = os.environ.get(
        "SOURCE_DOCUMENT_NODE_CANDIDATES_CALLBACK_URL",
        "",
    ).strip()
    if explicit_url:
        return explicit_url

    base_url = os.environ.get("EDNODA_CALLBACK_BASE_URL", "").strip()
    if not base_url:
        return None

    return f"{base_url.rstrip('/')}{NODE_CANDIDATES_CALLBACK_PATH}"


def post_node_candidates_callback(body: dict[str, Any]) -> None:
    callback_url = resolve_node_candidates_callback_url()
    if not callback_url:
        return

    post_signed_source_document_callback(
        callback_url,
        body,
        error_label="Source document node-candidates callback",
    )


def try_post_node_candidates_callback(body: dict[str, Any]) -> None:
    callback_url = resolve_node_candidates_callback_url()
    secret = os.environ.get("SOURCE_DOCUMENT_CALLBACK_SECRET", "").strip()
    if not callback_url or not secret:
        return
    post_node_candidates_callback(body)


def build_ubc_node_candidates_callback_body(
    handoff: UbcCandidateExtractionInputV1,
    result: dict[str, Any],
    *,
    attempt_number: int = 1,
) -> dict[str, Any]:
    """Build v1 node-candidates callback from UBC handoff input (task 10.6b)."""
    body: dict[str, Any] = {
        "version": CANDIDATE_EXTRACTION_RESULT_VERSION,
        "sourceDocumentId": handoff.source_document_id,
        "extractionId": handoff.extraction_id,
        "attemptNumber": attempt_number,
        "occurredAtIso": iso_timestamp(),
        "status": result["status"],
        "candidates": result.get("candidates") or [],
    }

    if handoff.callback.task_token:
        body["taskToken"] = handoff.callback.task_token

    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        body["warnings"] = warnings

    error = result.get("error")
    if isinstance(error, dict) and error:
        body["error"] = error

    return body


def post_node_candidates_callback_to_url(callback_url: str, body: dict[str, Any]) -> None:
    if not callback_url:
        return

    post_signed_source_document_callback(
        callback_url,
        body,
        error_label="Source document node-candidates callback",
    )


def try_post_ubc_node_candidates_callback(
    handoff: UbcCandidateExtractionInputV1,
    body: dict[str, Any],
) -> None:
    """POST signed callback to handoff.callback.url when secret is configured."""
    secret = os.environ.get("SOURCE_DOCUMENT_CALLBACK_SECRET", "").strip()
    if not handoff.callback.url or not secret:
        return
    post_node_candidates_callback_to_url(handoff.callback.url, body)
