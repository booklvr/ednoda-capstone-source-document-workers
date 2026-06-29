"""Tests for cross-chunk overlap de-duplication (Stage B).

See 062526-candidate-quality-language-hardening.md. The sliding-window chunker
overlaps adjacent chunks by whole sentences; this collapses that overlap so each
sentence is scored exactly once. No coverage loss: every unique sentence
survives in exactly one chunk.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[2]
STUB_DIR = WORKER_ROOT / "candidate-extractor-nlu"
for path in (WORKER_ROOT, STUB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chunk_dedup import dedupe_overlapping_chunks  # noqa: E402


def _chunk(chunk_id: str, index: int, text: str, block_ids: list[str]) -> dict:
    return {
        "chunkId": chunk_id,
        "index": index,
        "text": text,
        "wordCount": len(text.split()),
        "sourceBlockIds": block_ids,
    }


class DedupeOverlappingChunksTests(unittest.TestCase):
    def test_shared_sentence_appears_once_and_nothing_is_lost(self) -> None:
        chunks = [
            _chunk("chunk-000001", 0, "The dog runs. The cat sleeps.", ["b1"]),
            _chunk("chunk-000002", 1, "The cat sleeps. Birds can fly.", ["b1", "b2"]),
        ]

        result = dedupe_overlapping_chunks(chunks)

        all_text = " ".join(c["text"] for c in result)
        self.assertEqual(all_text.count("The cat sleeps."), 1)
        self.assertIn("The dog runs.", all_text)
        self.assertIn("Birds can fly.", all_text)

    def test_drops_chunk_fully_contained_in_overlap_without_losing_content(self) -> None:
        chunks = [
            _chunk("chunk-000001", 0, "Alpha one. Beta two.", ["b1"]),
            _chunk("chunk-000002", 1, "Beta two.", ["b1"]),  # entirely overlap
        ]

        result = dedupe_overlapping_chunks(chunks)

        self.assertEqual(len(result), 1)
        self.assertIn("Alpha one.", result[0]["text"])
        self.assertIn("Beta two.", result[0]["text"])

    def test_preserves_block_ids_and_recomputes_word_count(self) -> None:
        chunks = [
            _chunk("chunk-000001", 0, "One two three. Four five.", ["b1"]),
            _chunk("chunk-000002", 1, "Four five. Six.", ["b2"]),
        ]

        result = dedupe_overlapping_chunks(chunks)

        second = result[1]
        self.assertEqual(second["text"], "Six.")
        self.assertEqual(second["wordCount"], 1)
        self.assertEqual(second["sourceBlockIds"], ["b2"])

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(dedupe_overlapping_chunks([]), [])


if __name__ == "__main__":
    unittest.main()
