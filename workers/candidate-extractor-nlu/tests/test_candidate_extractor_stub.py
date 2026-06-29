"""Node-candidates callback signing/shape tests.

The old CandidateExtractorEvent handler-contract tests were removed when the
worker adopted Nick's UBC-handoff handler shape (see
test_nlu_candidate_extractor.py). These remaining tests cover the shared
callback helpers, which are still part of the contract surface.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[2]
STUB_DIR = WORKER_ROOT / "candidate-extractor-nlu"
for path in (WORKER_ROOT, STUB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared.contracts import (  # noqa: E402
    CANDIDATE_EXTRACTION_RESULT_VERSION,
    CANDIDATE_STATUS_READY,
)
from shared.event import OriginalFilePointer  # noqa: E402


class NodeCandidatesCallbackPostTests(unittest.TestCase):
    def test_sign_callback_body_is_deterministic(self) -> None:
        from shared.callback_post import sign_callback_body

        secret = "test-secret"
        raw_body = json.dumps({"a": 1}, separators=(",", ":"), sort_keys=True)
        first = sign_callback_body(secret, raw_body)
        second = sign_callback_body(secret, raw_body)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_build_node_candidates_callback_body_shape(self) -> None:
        from shared.callback_post import build_node_candidates_callback_body
        from shared.event import CandidateExtractorEvent, S3ObjectPointer

        event = CandidateExtractorEvent(
            environment="dev",
            source_document_id=42,
            owner_user_id="00000000-0000-4000-8000-000000000001",
            original=OriginalFilePointer(
                bucket="ednoda-dev-source-documents",
                key="source-documents/user/u/document/42/original/lesson.txt",
                mime_type="text/plain",
                file_extension=".txt",
                file_size_bytes=32,
            ),
            workflow_execution_arn=None,
            workflow_execution_row_id=None,
            attempt_number=1,
            original_filename="lesson.txt",
            extraction_id=7,
            plain_text=S3ObjectPointer(
                bucket="ednoda-dev-source-document-text",
                key="source-document-text/user/u/document/42/extraction/7/plain.txt",
            ),
            task_token="token-1",
        )
        body = build_node_candidates_callback_body(
            event,
            {
                "status": CANDIDATE_STATUS_READY,
                "candidates": [
                    {
                        "candidateType": "vocab",
                        "text": "term: definition",
                        "normalizedText": "term definition",
                    },
                ],
                "warnings": [],
            },
        )
        self.assertEqual(body["version"], CANDIDATE_EXTRACTION_RESULT_VERSION)
        self.assertEqual(body["extractionId"], 7)
        self.assertEqual(body["taskToken"], "token-1")


if __name__ == "__main__":
    unittest.main()
