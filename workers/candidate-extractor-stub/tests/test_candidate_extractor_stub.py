"""Unit tests for Alpha candidate extractor stub handler and callbacks."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WORKER_ROOT = Path(__file__).resolve().parents[2]
STUB_DIR = WORKER_ROOT / "candidate-extractor-stub"
for path in (WORKER_ROOT, STUB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared.contracts import (  # noqa: E402
    CANDIDATE_EXTRACTION_RESULT_VERSION,
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_READY,
    WARNING_NO_CANDIDATES_FOUND,
)
from shared.event import OriginalFilePointer  # noqa: E402


def load_stub_handler_module():
    spec = importlib.util.spec_from_file_location(
        "candidate_extractor_stub_handler_for_tests",
        STUB_DIR / "handler.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(**overrides: object) -> dict:
    base = {
        "environment": "dev",
        "sourceDocumentId": 42,
        "ownerUserId": "00000000-0000-4000-8000-000000000001",
        "extractionId": 7,
        "attemptNumber": 1,
        "original": {
            "bucket": "ednoda-dev-source-documents",
            "key": "source-documents/user/u/document/42/original/lesson.txt",
            "mimeType": "text/plain",
            "fileExtension": ".txt",
            "fileSizeBytes": 32,
        },
        "extractedTextPackage": {
            "manifest": {
                "bucket": "ednoda-dev-source-document-text",
                "key": "source-document-text/user/u/document/42/extraction/7/manifest.json",
            },
            "plainText": {
                "bucket": "ednoda-dev-source-document-text",
                "key": "source-document-text/user/u/document/42/extraction/7/plain.txt",
            },
        },
        "taskToken": "task-token-abc",
    }
    base.update(overrides)
    return base


class CandidateExtractorStubHandlerTests(unittest.TestCase):
    def test_handler_posts_ready_callback_with_candidates(self) -> None:
        handler_module = load_stub_handler_module()
        plain_text = "photosynthesis: energy from light\nWhat is photosynthesis?\n"

        class FakeBody:
            def read(self) -> bytes:
                return plain_text.encode("utf-8")

        class FakeClient:
            def get_object(self, *, Bucket: str, Key: str) -> dict:
                return {"Body": FakeBody()}

        with (
            patch.object(handler_module, "create_boto3_s3_client", return_value=FakeClient()),
            patch.object(
                handler_module,
                "try_post_node_candidates_callback",
            ) as post_callback,
        ):
            result = handler_module.handler(make_event(), None)

        self.assertEqual(result["status"], CANDIDATE_STATUS_READY)
        self.assertGreaterEqual(len(result["candidates"]), 2)
        post_callback.assert_called_once()
        body = post_callback.call_args.args[0]
        self.assertEqual(body["version"], CANDIDATE_EXTRACTION_RESULT_VERSION)
        self.assertEqual(body["sourceDocumentId"], 42)
        self.assertEqual(body["extractionId"], 7)
        self.assertEqual(body["taskToken"], "task-token-abc")
        self.assertGreaterEqual(len(body["candidates"]), 2)

    def test_handler_posts_ready_with_no_candidates_warning(self) -> None:
        handler_module = load_stub_handler_module()

        class FakeBody:
            def read(self) -> bytes:
                return b"   \n\n   "

        class FakeClient:
            def get_object(self, *, Bucket: str, Key: str) -> dict:
                return {"Body": FakeBody()}

        with (
            patch.object(handler_module, "create_boto3_s3_client", return_value=FakeClient()),
            patch.object(
                handler_module,
                "try_post_node_candidates_callback",
            ) as post_callback,
        ):
            result = handler_module.handler(make_event(), None)

        self.assertEqual(result["status"], CANDIDATE_STATUS_READY)
        self.assertEqual(result["candidates"], [])
        body = post_callback.call_args.args[0]
        self.assertIn(WARNING_NO_CANDIDATES_FOUND, body["warnings"])

    def test_handler_posts_failed_for_invalid_event(self) -> None:
        handler_module = load_stub_handler_module()

        with patch.object(
            handler_module,
            "try_post_node_candidates_callback",
        ) as post_callback:
            result = handler_module.handler({"sourceDocumentId": 42}, None)

        self.assertEqual(result["status"], CANDIDATE_STATUS_FAILED)
        post_callback.assert_not_called()


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
