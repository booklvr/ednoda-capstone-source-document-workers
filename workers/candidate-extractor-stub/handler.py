"""Alpha Source Document deterministic candidate extraction stub."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

WORKER_ROOT = Path(__file__).resolve().parents[1]
STUB_DIR = Path(__file__).resolve().parent
for path in (WORKER_ROOT, STUB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from heuristics import extract_candidates_from_plain_text  # noqa: E402
from shared.callback_post import (  # noqa: E402
    build_node_candidates_callback_body,
    try_post_node_candidates_callback,
)
from shared.contracts import (  # noqa: E402
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_READY,
    WARNING_NO_CANDIDATES_FOUND,
)
from shared.event import (  # noqa: E402
    CandidateExtractorEvent,
    WorkerEventError,
    parse_candidate_extractor_event,
)
from shared.s3_client import create_boto3_s3_client, read_object_bytes  # noqa: E402
from shared.worker_errors import is_transient_infrastructure_error  # noqa: E402


def build_candidate_branch_result(
    *,
    status: str,
    candidates: list[dict[str, Any]],
    warnings: list[str] | None = None,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "candidates": candidates,
        "warnings": warnings or [],
        "error": error,
    }


def process_candidate_extraction(
    event: CandidateExtractorEvent,
    *,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    client = s3_client or create_boto3_s3_client()
    try:
        raw = read_object_bytes(
            client,
            bucket=event.plain_text.bucket,
            key=event.plain_text.key,
        )
        plain_text = raw.decode("utf-8")
    except Exception as error:
        if is_transient_infrastructure_error(error):
            raise
        return build_candidate_branch_result(
            status=CANDIDATE_STATUS_FAILED,
            candidates=[],
            error={
                "code": "plain_text_unreadable",
                "message": str(error),
            },
        )

    candidates = extract_candidates_from_plain_text(plain_text)
    warnings: list[str] = []
    if not candidates:
        warnings.append(WARNING_NO_CANDIDATES_FOUND)

    return build_candidate_branch_result(
        status=CANDIDATE_STATUS_READY,
        candidates=candidates,
        warnings=warnings or None,
    )


def handler(event: dict[str, Any], _context: Any | None = None) -> dict[str, Any]:
    try:
        parsed = parse_candidate_extractor_event(event)
    except WorkerEventError as error:
        result = build_candidate_branch_result(
            status=CANDIDATE_STATUS_FAILED,
            candidates=[],
            error={"code": "invalid_event", "message": str(error)},
        )
        return result

    try:
        result = process_candidate_extraction(parsed)
    except Exception as error:
        if is_transient_infrastructure_error(error):
            raise
        result = build_candidate_branch_result(
            status=CANDIDATE_STATUS_FAILED,
            candidates=[],
            error={
                "code": "candidate_extraction_failed",
                "message": str(error),
            },
        )

    callback_body = build_node_candidates_callback_body(parsed, result)
    try_post_node_candidates_callback(callback_body)
    return result
