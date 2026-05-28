"""
Local UBC adapter/stub harness (task 10.6b).

Receives the exact SourceDocumentCandidateExtractionInputV1 handoff payload,
validates it, returns a deterministic dummy success result, and optionally POSTs
through the signed node-candidates callback URL from the handoff (same boundary
as production UBC). Not for real UBC dispatch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

WORKER_ROOT = Path(__file__).resolve().parents[1]
STUB_DIR = Path(__file__).resolve().parent
for path in (WORKER_ROOT, STUB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared.callback_post import (  # noqa: E402
    build_ubc_node_candidates_callback_body,
    try_post_ubc_node_candidates_callback,
)
from shared.contracts import (  # noqa: E402
    CANDIDATE_STATUS_READY,
    CANDIDATE_TYPE_QUESTION,
    CANDIDATE_TYPE_VOCAB,
    WARNING_UBC_LOCAL_STUB_DUMMY,
)
from shared.event import WorkerEventError  # noqa: E402
from shared.ubc_input import (  # noqa: E402
    UbcCandidateExtractionInputV1,
    parse_ubc_candidate_extraction_input_v1,
)


def build_dummy_ubc_extraction_result(
    handoff: UbcCandidateExtractionInputV1,
) -> dict[str, Any]:
    """Deterministic dummy candidates — no S3 reads (local/stub only)."""
    document_id = handoff.source_document_id
    extraction_id = handoff.extraction_id
    filename = handoff.original.filename

    return {
        "status": CANDIDATE_STATUS_READY,
        "candidates": [
            {
                "candidateType": CANDIDATE_TYPE_VOCAB,
                "text": f"{filename}: ubc-local-stub vocabulary",
                "normalizedText": f"doc-{document_id}-ext-{extraction_id}-vocab",
                "promptText": None,
                "answerText": None,
                "sourceBlockId": None,
                "sourcePageNumber": None,
                "sourceSlideNumber": None,
                "confidence": 1.0,
                "metadata": {
                    "source": "ubc_local_stub",
                    "mode": "dummy",
                    "environment": handoff.environment,
                },
            },
            {
                "candidateType": CANDIDATE_TYPE_QUESTION,
                "text": f"What did ubc-local-stub extract from document {document_id}?",
                "normalizedText": (
                    f"doc-{document_id}-ext-{extraction_id}-question"
                ),
                "promptText": (
                    f"What did ubc-local-stub extract from document {document_id}?"
                ),
                "answerText": "Deterministic stub answer (not from S3).",
                "sourceBlockId": None,
                "sourcePageNumber": None,
                "sourceSlideNumber": None,
                "confidence": 1.0,
                "metadata": {
                    "source": "ubc_local_stub",
                    "mode": "dummy",
                },
            },
        ],
        "warnings": [WARNING_UBC_LOCAL_STUB_DUMMY],
        "error": None,
    }


def run_ubc_local_stub_handoff(
    handoff_payload: dict[str, Any],
    *,
    attempt_number: int = 1,
    post_callback: bool = True,
) -> dict[str, Any]:
    """
    Validate v1 handoff, build dummy success output, optionally POST callback.

    Returns extraction branch result and the callback body (for tests without network).
    """
    try:
        handoff = parse_ubc_candidate_extraction_input_v1(handoff_payload)
    except WorkerEventError as error:
        return {
            "status": "invalid_handoff",
            "error": {"code": "invalid_handoff", "message": str(error)},
        }

    result = build_dummy_ubc_extraction_result(handoff)
    callback_body = build_ubc_node_candidates_callback_body(
        handoff,
        result,
        attempt_number=attempt_number,
    )

    if post_callback:
        try_post_ubc_node_candidates_callback(handoff, callback_body)

    return {
        "status": "stub_completed",
        "handoffMode": "ubc_local_stub",
        "extractionResult": result,
        "callbackBody": callback_body,
    }


def handler(event: dict[str, Any], _context: Any | None = None) -> dict[str, Any]:
    """Lambda-style entrypoint: event is the v1 handoff object."""
    return run_ubc_local_stub_handoff(event)
