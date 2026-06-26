"""Tests for candidate quality pruning + redundancy reduction (Stage D).

See 062526-candidate-quality-language-hardening.md. Reduction is earned through
quality (drop fragments, collapse near-duplicates), not an arbitrary cap. A high
safety ceiling only triggers a type-balanced truncation to protect review/payload.
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

from candidate_pruner import prune_candidates  # noqa: E402


def _cand(text: str, candidate_type: str = "vocab", confidence: float = 0.8) -> dict:
    return {
        "candidateType": candidate_type,
        "text": text,
        "normalizedText": text.lower().strip(),
        "confidence": confidence,
        "metadata": {},
    }


class PruneCandidatesTests(unittest.TestCase):
    def test_drops_low_quality_fragments(self) -> None:
        candidates = [
            _cand("photosynthesis"),
            _cand("the"),     # single stopword
            _cand("12"),      # numeric only
            _cand("a"),       # single char
            _cand("   "),     # empty
        ]

        result = prune_candidates(candidates)

        texts = [c["text"] for c in result.candidates]
        self.assertIn("photosynthesis", texts)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.stats["droppedLowQuality"], 4)

    def test_collapses_inflectional_and_determiner_duplicates(self) -> None:
        candidates = [
            _cand("listen", confidence=0.70),
            _cand("listening", confidence=0.90),
            _cand("a dog", candidate_type="expression", confidence=0.75),
            _cand("the dog", candidate_type="expression", confidence=0.85),
        ]

        result = prune_candidates(candidates)

        texts = [c["text"] for c in result.candidates]
        # one survivor per near-duplicate group, the higher-confidence one
        self.assertEqual(len(result.candidates), 2)
        self.assertIn("listening", texts)
        self.assertIn("the dog", texts)
        self.assertEqual(result.stats["collapsedDuplicates"], 2)

    def test_keeps_distinct_candidates(self) -> None:
        candidates = [_cand("dog"), _cand("cat"), _cand("run")]

        result = prune_candidates(candidates)

        self.assertEqual(len(result.candidates), 3)

    def test_safety_ceiling_truncates_with_type_balance(self) -> None:
        candidates = [
            _cand("alpha", confidence=0.90),
            _cand("beta", confidence=0.88),
            _cand("gamma", confidence=0.86),
            _cand("delta", confidence=0.84),
            _cand("What is alpha?", candidate_type="question", confidence=0.60),
        ]

        result = prune_candidates(candidates, max_candidates=3)

        self.assertEqual(len(result.candidates), 3)
        types = {c["candidateType"] for c in result.candidates}
        # the lone (low-confidence) question survives truncation for balance
        self.assertIn("question", types)
        self.assertEqual(result.stats["ceilingApplied"], 1)

    def test_no_ceiling_keeps_all(self) -> None:
        candidates = [_cand(f"word{i}", confidence=0.5) for i in range(50)]

        result = prune_candidates(candidates, max_candidates=None)

        self.assertEqual(len(result.candidates), 50)
        self.assertEqual(result.stats["ceilingApplied"], 0)


if __name__ == "__main__":
    unittest.main()
