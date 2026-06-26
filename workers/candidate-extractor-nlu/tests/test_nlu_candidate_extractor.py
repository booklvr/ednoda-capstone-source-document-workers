"""Contract tests for the Ednoda NLU candidate extractor handler.

Ported from Nick's integrated test suite and adapted to our directory layout.
These lock the UBC-handoff handler shape (S3 read, grammar->expression
normalization, compact summary return, signed callback body).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import Any

WORKER_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = WORKER_ROOT / "candidate-extractor-nlu"
for path in (WORKER_ROOT, WORKER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class _Body:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value


class FakeS3Client:
    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self.objects = objects

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        return {"Body": _Body(self.objects[(Bucket, Key)])}


def load_handler_module():
    spec = importlib.util.spec_from_file_location(
        "candidate_extractor_nlu_handler_for_tests",
        WORKER_DIR / "handler.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_v1_handoff() -> dict[str, Any]:
    return {
        "version": "source-document-candidate-extraction.v1",
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


def make_fake_s3() -> FakeS3Client:
    bucket = "ednoda-dev-source-document-text"
    manifest_key = "source-document-text/user/u/document/42/extraction/7/manifest.json"
    plain_key = "source-document-text/user/u/document/42/extraction/7/plain.txt"
    block_key = "source-document-text/user/u/document/42/extraction/7/blocks/block-000001.json"
    manifest = {
        "version": "ednoda.extracted-source-document.v1",
        "outputs": {
            "plainText": {"bucket": bucket, "key": plain_key},
            "blockIndex": [
                {
                    "blockId": "block-000001",
                    "bucket": bucket,
                    "key": block_key,
                    "blockType": "paragraph",
                    "charCount": 30,
                },
            ],
            "chunks": [],
        },
    }
    block = {
        "version": "ednoda.extracted-source-document-block.v1",
        "sourceDocumentId": 42,
        "extractionId": 7,
        "blockId": "block-000001",
        "source": {"pageNumber": 2},
        "blockType": "paragraph",
        "text": "She is listening to music.",
    }
    return FakeS3Client(
        {
            (bucket, manifest_key): json.dumps(manifest).encode("utf-8"),
            (bucket, plain_key): b"She is listening to music.",
            (bucket, block_key): json.dumps(block).encode("utf-8"),
        },
    )


class CandidateExtractorNluTests(unittest.TestCase):
    def test_normalizes_student_grammar_type_to_ednoda_expression(self) -> None:
        module = load_handler_module()

        candidate = module.normalize_candidate_for_ednoda(
            {
                "candidateType": "grammar",
                "text": "She is listening to music.",
                "normalizedText": "she is listening to music.",
                "metadata": {"engine": "dependency_matcher"},
            },
        )

        self.assertEqual(candidate["candidateType"], "expression")
        self.assertEqual(candidate["metadata"]["nluCandidateType"], "grammar")
        self.assertEqual(candidate["metadata"]["engine"], "dependency_matcher")

    def test_maps_unrecognized_candidate_type_to_unknown(self) -> None:
        module = load_handler_module()

        candidate = module.normalize_candidate_for_ednoda(
            {
                "candidateType": "dialogue",
                "text": "Hello there.",
                "normalizedText": "hello there.",
                "metadata": {},
            },
        )

        self.assertEqual(candidate["candidateType"], "unknown")
        self.assertEqual(candidate["metadata"]["nluCandidateType"], "dialogue")
        self.assertEqual(
            candidate["metadata"]["contractNormalization"],
            "mapped_to_unknown",
        )

    def test_runs_handoff_and_builds_contract_safe_callback(self) -> None:
        module = load_handler_module()

        class FakeLabeller:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def label(self, chunks: list[dict], blocks: list[dict]) -> list[dict]:
                if not chunks:
                    raise AssertionError("Expected chunks")
                if blocks[0]["blockId"] != "block-000001":
                    raise AssertionError("Expected source block provenance")
                return [
                    {
                        "candidateType": "grammar",
                        "text": "She is listening to music.",
                        "normalizedText": "she is listening to music.",
                        "sourceBlockId": "block-000001",
                        "sourcePageNumber": 2,
                        "sourceSlideNumber": None,
                        "confidence": 0.8,
                        "metadata": {
                            "engine": "dependency_matcher",
                            "patterns": ["present_continuous"],
                        },
                    },
                ]

        module.NLULabeller = FakeLabeller

        output = module.run_nlu_candidate_extraction_handoff(
            make_v1_handoff(),
            attempt_number=3,
            s3_client=make_fake_s3(),
            post_callback=False,
            include_debug_payloads=True,
        )

        self.assertEqual(output["status"], "ready")
        self.assertEqual(output["candidateCount"], 1)
        body = output["callbackBody"]
        self.assertEqual(
            body["version"],
            "source-document-candidate-extraction-result.v1",
        )
        self.assertEqual(body["sourceDocumentId"], 42)
        self.assertEqual(body["extractionId"], 7)
        self.assertEqual(body["attemptNumber"], 3)
        self.assertEqual(body["taskToken"], "task-token-abc")
        candidate = body["candidates"][0]
        self.assertEqual(candidate["candidateType"], "expression")
        self.assertEqual(candidate["metadata"]["nluCandidateType"], "grammar")
        self.assertEqual(candidate["metadata"]["patterns"], ["present_continuous"])

    def test_handler_never_raises_on_malformed_event(self) -> None:
        module = load_handler_module()

        # A non-dict event must not raise out of the Lambda handler.
        result = module.handler([], None)

        self.assertIn(result.get("status"), {"invalid_handoff", "failed"})

    def test_handler_returns_invalid_for_empty_event(self) -> None:
        module = load_handler_module()

        result = module.handler({}, None)

        self.assertEqual(result["status"], "invalid_handoff")

    def test_handoff_returns_compact_summary_by_default(self) -> None:
        module = load_handler_module()

        class FakeLabeller:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def label(self, chunks: list[dict], blocks: list[dict]) -> list[dict]:
                return [
                    {
                        "candidateType": "vocab",
                        "text": f"candidate {index}",
                        "normalizedText": f"candidate {index}",
                        "sourceBlockId": "block-000001",
                        "sourcePageNumber": 2,
                        "confidence": 0.5,
                        "metadata": {"index": index},
                    }
                    for index in range(100)
                ]

        module.NLULabeller = FakeLabeller

        output = module.run_nlu_candidate_extraction_handoff(
            make_v1_handoff(),
            s3_client=make_fake_s3(),
            post_callback=False,
        )

        self.assertEqual(output["status"], "ready")
        self.assertEqual(output["candidateCount"], 100)
        self.assertNotIn("callbackBody", output)
        self.assertNotIn("extractionResult", output)


if __name__ == "__main__":
    unittest.main()
