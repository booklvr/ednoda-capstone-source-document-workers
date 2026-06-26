"""A-E wiring on the UBC-handoff handler (re-applied after reconciliation).

See 062526-candidate-quality-language-hardening.md. Verifies Stage A (language
gate on plain text AND blocks), Stage B (chunk dedupe), and Stage D (pruning)
are wired into process_candidate_extraction.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

WORKER_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = WORKER_ROOT / "candidate-extractor-nlu"
for path in (WORKER_ROOT, WORKER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

_BUCKET = "ednoda-dev-source-document-text"
_MANIFEST_KEY = "source-document-text/user/u/document/42/extraction/7/manifest.json"
_PLAIN_KEY = "source-document-text/user/u/document/42/extraction/7/plain.txt"


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
        "candidate_extractor_handler_preproc_tests",
        WORKER_DIR / "handler.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_handoff() -> dict[str, Any]:
    return {
        "version": "source-document-candidate-extraction.v1",
        "environment": "dev",
        "sourceDocumentId": 42,
        "extractionId": 7,
        "target": {"targetType": "lesson", "lessonId": 101, "defaultQuestionListId": 55},
        "extractedTextPackage": {
            "manifest": {"bucket": _BUCKET, "key": _MANIFEST_KEY},
            "plainText": {"bucket": _BUCKET, "key": _PLAIN_KEY},
            "chunksPrefix": {"bucket": _BUCKET, "prefix": "x/chunks/"},
            "blocksPrefix": {"bucket": _BUCKET, "prefix": "x/blocks/"},
        },
        "original": {"filename": "lesson.txt", "mimeType": "text/plain", "fileExtension": ".txt"},
        "callback": {
            "url": "https://nick-dev.ednoda.com/api/source-documents/node-candidates/callback",
            "signingHeader": "X-Ednoda-Signature",
            "taskToken": "task-token-abc",
        },
    }


def make_fake_s3(plain_text: str, block_texts: list[str]) -> FakeS3Client:
    objects: dict[tuple[str, str], bytes] = {}
    block_index = []
    for index, text in enumerate(block_texts, start=1):
        block_id = f"block-{index:06d}"
        key = f"source-document-text/user/u/document/42/extraction/7/blocks/{block_id}.json"
        block_index.append({"blockId": block_id, "bucket": _BUCKET, "key": key, "blockType": "paragraph"})
        objects[(_BUCKET, key)] = json.dumps(
            {"blockId": block_id, "source": {"pageNumber": index}, "text": text}
        ).encode("utf-8")
    manifest = {
        "version": "ednoda.extracted-source-document.v1",
        "outputs": {"plainText": {"bucket": _BUCKET, "key": _PLAIN_KEY}, "blockIndex": block_index},
    }
    objects[(_BUCKET, _MANIFEST_KEY)] = json.dumps(manifest).encode("utf-8")
    objects[(_BUCKET, _PLAIN_KEY)] = plain_text.encode("utf-8")
    return FakeS3Client(objects)


def _parse(module, handoff: dict) -> Any:
    return module.parse_ubc_candidate_extraction_input_v1(handoff)


class HandlerPreprocessingTests(unittest.TestCase):
    def test_language_gate_applies_to_plain_text_and_blocks(self) -> None:
        module = load_handler_module()
        plain_text = "\n".join(
            ["Cool Book", "안녕하세요 여러분", "Cool Book", "The dog runs.",
             "Cool Book", "Page 5", "Cool Book", "We sing songs.", "Cool Book"]
        )
        captured: dict[str, list[dict]] = {}

        class FakeLabeller:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def label(self, chunks: list[dict], blocks: list[dict]) -> list[dict]:
                captured["chunks"] = chunks
                captured["blocks"] = blocks
                return []

        module.NLULabeller = FakeLabeller
        fake = make_fake_s3(plain_text, ["안녕하세요 여러분", "Birds can fly."])
        module.process_candidate_extraction(_parse(module, make_handoff()), s3_client=fake)

        chunk_text = " ".join(c.get("text", "") for c in captured["chunks"])
        self.assertIn("The dog runs", chunk_text)
        self.assertIn("We sing songs", chunk_text)
        self.assertNotIn("안녕하세요", chunk_text)
        self.assertNotIn("Cool Book", chunk_text)
        self.assertNotIn("Page 5", chunk_text)

        block_text = " ".join(b.get("text", "") for b in captured["blocks"])
        self.assertIn("Birds can fly", block_text)
        self.assertNotIn("안녕하세요", block_text)

    def test_chunks_are_deduped_before_labelling(self) -> None:
        module = load_handler_module()
        captured: dict[str, object] = {}
        sentinel = [{"chunkId": "deduped", "index": 0, "text": "X", "wordCount": 1, "sourceBlockIds": []}]

        def fake_dedupe(chunks: list[dict]) -> list[dict]:
            captured["dedupe_input"] = chunks
            return sentinel

        class FakeLabeller:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def label(self, chunks: list[dict], blocks: list[dict]) -> list[dict]:
                captured["labeller_chunks"] = chunks
                return []

        module.NLULabeller = FakeLabeller
        fake = make_fake_s3("The dog runs. The cat sleeps.", ["The dog runs. The cat sleeps."])
        with patch.object(module, "dedupe_overlapping_chunks", fake_dedupe):
            module.process_candidate_extraction(_parse(module, make_handoff()), s3_client=fake)

        self.assertIn("dedupe_input", captured)
        self.assertIs(captured["labeller_chunks"], sentinel)

    def test_candidates_are_pruned_before_result(self) -> None:
        module = load_handler_module()

        class FakeLabeller:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def label(self, chunks: list[dict], blocks: list[dict]) -> list[dict]:
                return [
                    {"candidateType": "vocab", "text": "photosynthesis",
                     "normalizedText": "photosynthesis", "confidence": 0.9, "metadata": {}},
                    {"candidateType": "vocab", "text": "the",
                     "normalizedText": "the", "confidence": 0.5, "metadata": {}},
                ]

        module.NLULabeller = FakeLabeller
        fake = make_fake_s3("Some English content here.", ["Some English content here."])
        result = module.process_candidate_extraction(_parse(module, make_handoff()), s3_client=fake)

        texts = [c["text"] for c in result["candidates"]]
        self.assertIn("photosynthesis", texts)
        self.assertNotIn("the", texts)


if __name__ == "__main__":
    unittest.main()
