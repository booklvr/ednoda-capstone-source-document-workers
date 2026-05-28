"""Unit tests for local UBC adapter/stub harness (task 10.6b)."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

WORKER_ROOT = Path(__file__).resolve().parents[2]
STUB_DIR = WORKER_ROOT / "candidate-extractor-stub"
for path in (WORKER_ROOT, STUB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared.contracts import (  # noqa: E402
    CANDIDATE_EXTRACTION_INPUT_VERSION,
    CANDIDATE_EXTRACTION_RESULT_VERSION,
    CANDIDATE_STATUS_READY,
    WARNING_UBC_LOCAL_STUB_DUMMY,
)


def load_ubc_adapter_module():
    spec = importlib.util.spec_from_file_location(
        "ubc_local_adapter_for_tests",
        STUB_DIR / "ubc_local_adapter.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_v1_handoff(**overrides: object) -> dict:
    base = {
        "version": CANDIDATE_EXTRACTION_INPUT_VERSION,
        "environment": "dev",
        "sourceDocumentId": 42,
        "extractionId": 7,
        "target": {
            "targetType": "lesson",
            "lessonId": 101,
            "defaultQuestionListId": 55,
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
            "chunksPrefix": {
                "bucket": "ednoda-dev-source-document-text",
                "prefix": "source-document-text/user/u/document/42/extraction/7/chunks/",
            },
            "blocksPrefix": {
                "bucket": "ednoda-dev-source-document-text",
                "prefix": "source-document-text/user/u/document/42/extraction/7/blocks/",
            },
        },
        "original": {
            "filename": "lesson-vocab.txt",
            "mimeType": "text/plain",
            "fileExtension": ".txt",
        },
        "callback": {
            "url": "https://nick-dev.ednoda.com/api/source-documents/node-candidates/callback",
            "signingHeader": "X-Ednoda-Signature",
            "taskToken": "task-token-abc",
        },
    }
    base.update(overrides)
    return base


class UbcLocalAdapterTests(unittest.TestCase):
    def test_run_stub_returns_dummy_ready_result_without_inline_text(self) -> None:
        adapter = load_ubc_adapter_module()
        handoff = make_v1_handoff()

        with patch.object(adapter, "try_post_ubc_node_candidates_callback") as post_callback:
            output = adapter.run_ubc_local_stub_handoff(handoff, post_callback=False)

        self.assertEqual(output["status"], "stub_completed")
        self.assertEqual(output["handoffMode"], "ubc_local_stub")

        result = output["extractionResult"]
        self.assertEqual(result["status"], CANDIDATE_STATUS_READY)
        self.assertGreaterEqual(len(result["candidates"]), 1)
        self.assertIn(WARNING_UBC_LOCAL_STUB_DUMMY, result["warnings"])

        serialized = json.dumps(output)
        self.assertNotIn("plain.txt contents", serialized)
        self.assertNotIn("block-000001", serialized)

        callback_body = output["callbackBody"]
        self.assertEqual(callback_body["version"], CANDIDATE_EXTRACTION_RESULT_VERSION)
        self.assertEqual(callback_body["sourceDocumentId"], 42)
        self.assertEqual(callback_body["extractionId"], 7)
        self.assertEqual(callback_body["taskToken"], "task-token-abc")
        self.assertEqual(callback_body["status"], CANDIDATE_STATUS_READY)
        post_callback.assert_not_called()

    def test_run_stub_posts_to_handoff_callback_url_when_secret_configured(self) -> None:
        adapter = load_ubc_adapter_module()
        handoff = make_v1_handoff()

        with (
            patch.object(adapter, "try_post_ubc_node_candidates_callback") as post_callback,
        ):
            adapter.run_ubc_local_stub_handoff(handoff)

        post_callback.assert_called_once()
        callback_body = post_callback.call_args.args[1]
        self.assertEqual(callback_body["version"], CANDIDATE_EXTRACTION_RESULT_VERSION)

    @patch("shared.callback_post.httpx.post")
    def test_post_ubc_callback_uses_handoff_url_and_signature(self, post_mock) -> None:
        from shared.callback_post import (
            build_ubc_node_candidates_callback_body,
            post_node_candidates_callback_to_url,
        )
        from shared.ubc_input import parse_ubc_candidate_extraction_input_v1

        handoff = parse_ubc_candidate_extraction_input_v1(make_v1_handoff())
        result = {
            "status": CANDIDATE_STATUS_READY,
            "candidates": [
                {
                    "candidateType": "vocab",
                    "text": "term: definition",
                    "normalizedText": "term definition",
                },
            ],
            "warnings": [],
        }
        body = build_ubc_node_candidates_callback_body(handoff, result)

        captured: dict[str, object] = {}

        def capture_request(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            content = kwargs["content"]
            captured["body"] = (
                content.decode("utf-8") if isinstance(content, bytes) else content
            )
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
            )

        post_mock.side_effect = capture_request

        with patch.dict(
            "os.environ",
            {"SOURCE_DOCUMENT_CALLBACK_SECRET": "test-secret"},
            clear=False,
        ):
            post_node_candidates_callback_to_url(handoff.callback.url, body)

        self.assertEqual(captured["url"], handoff.callback.url)
        headers = captured["headers"]
        self.assertIn("X-Ednoda-Signature", headers)
        self.assertEqual(headers["User-Agent"], "EdnodaSourceDocumentWorker/1.0")
        self.assertNotIn("test-secret", str(headers))
        self.assertNotIn("test-secret", captured["body"])

    def test_rejects_invalid_handoff_version(self) -> None:
        adapter = load_ubc_adapter_module()
        handoff = make_v1_handoff(version="wrong-version")

        output = adapter.run_ubc_local_stub_handoff(handoff, post_callback=False)

        self.assertEqual(output["status"], "invalid_handoff")
        self.assertIn("version", output["error"]["message"])

    def test_accepts_textbook_unit_target_handoff(self) -> None:
        adapter = load_ubc_adapter_module()
        handoff = make_v1_handoff(
            target={
                "targetType": "textbook_unit",
                "textbookId": 12,
                "textbookUnitId": 34,
            },
            callback={
                "url": "https://nick-dev.ednoda.com/api/source-documents/node-candidates/callback",
                "signingHeader": "X-Ednoda-Signature",
                "taskToken": None,
            },
        )

        output = adapter.run_ubc_local_stub_handoff(handoff, post_callback=False)

        self.assertEqual(output["status"], "stub_completed")
        self.assertIsNone(output["callbackBody"].get("taskToken"))


if __name__ == "__main__":
    unittest.main()
