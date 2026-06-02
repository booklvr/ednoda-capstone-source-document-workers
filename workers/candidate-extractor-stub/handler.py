"""Alpha Source Document NLU candidate extraction handler."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

WORKER_ROOT = Path(__file__).resolve().parents[1]
STUB_DIR = Path(__file__).resolve().parent
for path in (WORKER_ROOT, STUB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chunker import SlidingWindowChunker  # noqa: E402
from labeller import NLULabeller  # noqa: E402
from shared.callback_post import (  # noqa: E402
    build_node_candidates_callback_body,
    try_post_node_candidates_callback,
)
from shared.contracts import (  # noqa: E402
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_READY,
)
from shared.event import (  # noqa: E402
    CandidateExtractorEvent,
    WorkerEventError,
    parse_candidate_extractor_event,
)
from shared.s3_client import create_boto3_s3_client, read_object_bytes  # noqa: E402
from shared.worker_errors import is_transient_infrastructure_error  # noqa: E402

# "partial" is not yet in shared/contracts.py as a candidate status literal
_CANDIDATE_STATUS_PARTIAL = "partial"
_WARNING_NLU_NO_CANDIDATES = "NLU labeller returned no candidates"

logger = logging.getLogger(__name__)


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

    # Blocks are not carried in CandidateExtractorEvent; pass [] so chunker
    # and labeller operate gracefully without source-block attribution.
    chunker = SlidingWindowChunker()
    chunks = chunker.chunk(plain_text, [])

    labeller = NLULabeller()
    candidates = labeller.label(chunks, [])

    warnings: list[str] = []
    if not candidates:
        warnings.append(_WARNING_NLU_NO_CANDIDATES)
        status = _CANDIDATE_STATUS_PARTIAL
    else:
        status = CANDIDATE_STATUS_READY

    return build_candidate_branch_result(
        status=status,
        candidates=candidates,
        warnings=warnings or None,
    )


def handler(event: dict[str, Any], _context: Any | None = None) -> dict[str, Any]:
    document_id = event.get("sourceDocumentId", "unknown")
    extraction_id = event.get("extractionId", "unknown")
    logger.info(
        "candidate-extractor start documentId=%s extractionId=%s",
        document_id,
        extraction_id,
    )

    try:
        parsed = parse_candidate_extractor_event(event)
    except WorkerEventError as error:
        result = build_candidate_branch_result(
            status=CANDIDATE_STATUS_FAILED,
            candidates=[],
            error={"code": "invalid_event", "message": str(error)},
        )
        logger.info(
            "candidate-extractor end documentId=%s extractionId=%s status=%s",
            document_id,
            extraction_id,
            result["status"],
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
        try:
            callback_body = build_node_candidates_callback_body(parsed, result)
            try_post_node_candidates_callback(callback_body)
        except Exception:
            pass
        logger.info(
            "candidate-extractor end documentId=%s extractionId=%s status=failed",
            document_id,
            extraction_id,
        )
        return {"statusCode": 500}

    callback_body = build_node_candidates_callback_body(parsed, result)
    try_post_node_candidates_callback(callback_body)
    logger.info(
        "candidate-extractor end documentId=%s extractionId=%s status=%s",
        document_id,
        extraction_id,
        result["status"],
    )
    return {"statusCode": 200}
