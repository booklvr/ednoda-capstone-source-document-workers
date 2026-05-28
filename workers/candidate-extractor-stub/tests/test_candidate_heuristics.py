"""Unit tests for Alpha candidate extraction heuristics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[2]
STUB_DIR = WORKER_ROOT / "candidate-extractor-stub"
for path in (WORKER_ROOT, STUB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from heuristics import (  # noqa: E402
    classify_line_candidate,
    dedupe_candidates,
    detect_expression_candidates,
    extract_candidates_from_plain_text,
    normalize_candidate_text,
)
from shared.contracts import (  # noqa: E402
    CANDIDATE_TYPE_EXPRESSION,
    CANDIDATE_TYPE_QUESTION,
    CANDIDATE_TYPE_VOCAB,
)


class NormalizeCandidateTextTests(unittest.TestCase):
    def test_normalizes_case_whitespace_and_punctuation(self) -> None:
        self.assertEqual(
            normalize_candidate_text('  What is "Go"?  '),
            "what is go",
        )


class ClassifyLineCandidateTests(unittest.TestCase):
    def test_detects_question_lines(self) -> None:
        candidate = classify_line_candidate("What is photosynthesis?", 3)
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate["candidateType"], CANDIDATE_TYPE_QUESTION)
        self.assertEqual(candidate["sourceBlockId"], "line-000003")

    def test_detects_vocabulary_colon_pattern(self) -> None:
        candidate = classify_line_candidate("photosynthesis: energy from light", 2)
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate["candidateType"], CANDIDATE_TYPE_VOCAB)

    def test_detects_vocabulary_dash_pattern(self) -> None:
        candidate = classify_line_candidate("past tense - verb form for past actions", 4)
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate["candidateType"], CANDIDATE_TYPE_VOCAB)

    def test_ignores_noise_and_overlong_lines(self) -> None:
        self.assertIsNone(classify_line_candidate("", 1))
        self.assertIsNone(classify_line_candidate("---", 1))
        self.assertIsNone(classify_line_candidate("Slide 4", 1))
        self.assertIsNone(classify_line_candidate("Copyright 2026 Ednoda", 1))
        self.assertIsNone(
            classify_line_candidate("x" * 600, 1),
        )


class ExpressionHeuristicTests(unittest.TestCase):
    def test_detects_repeated_short_phrases(self) -> None:
        lines = [
            "Use past tense verbs in your answer.",
            "Remember past tense verbs when writing.",
            "Unrelated sentence without the phrase.",
        ]
        candidates = detect_expression_candidates(lines)
        types = {candidate["candidateType"] for candidate in candidates}
        self.assertIn(CANDIDATE_TYPE_EXPRESSION, types)
        self.assertTrue(
            any(
                "past tense" in candidate["text"]
                for candidate in candidates
            ),
        )


class ExtractCandidatesTests(unittest.TestCase):
    def test_extracts_mixed_candidates_and_dedupes(self) -> None:
        plain_text = "\n".join(
            [
                "photosynthesis: energy from light",
                "What is photosynthesis?",
                "Use past tense verbs here.",
                "Another past tense verbs example.",
                "photosynthesis: energy from light",
            ],
        )
        candidates = extract_candidates_from_plain_text(plain_text)
        types = {candidate["candidateType"] for candidate in candidates}
        self.assertIn(CANDIDATE_TYPE_VOCAB, types)
        self.assertIn(CANDIDATE_TYPE_QUESTION, types)
        self.assertIn(CANDIDATE_TYPE_EXPRESSION, types)
        self.assertEqual(
            len(candidates),
            len(dedupe_candidates(candidates)),
        )

    def test_returns_empty_for_blank_text(self) -> None:
        self.assertEqual(extract_candidates_from_plain_text("   \n\n  "), [])

    def test_filters_repeated_deck_title_before_expression_detection(self) -> None:
        plain_text = "\n".join(
            [
                "Lesson Deck",
                "photosynthesis: energy from light",
                "Lesson Deck",
                "What is chlorophyll?",
                "Lesson Deck",
                "Plants make sugar.",
            ],
        )

        candidates = extract_candidates_from_plain_text(plain_text)

        self.assertFalse(
            any(candidate["text"] == "lesson deck" for candidate in candidates),
        )
        self.assertTrue(
            any(candidate["candidateType"] == CANDIDATE_TYPE_VOCAB for candidate in candidates),
        )


class ExtractCandidatesTypeTests(unittest.TestCase):
    def test_stub_candidate_types_are_limited_to_vocab_expression_question(self) -> None:
        plain_text = "\n".join(
            [
                "photosynthesis: energy from light",
                "What is photosynthesis?",
                "Use past tense verbs here.",
                "Another past tense verbs example.",
                "Unclassified body paragraph without a heuristic match.",
            ],
        )
        candidates = extract_candidates_from_plain_text(plain_text)
        types = {candidate["candidateType"] for candidate in candidates}

        self.assertTrue(types.issubset(
            {
                CANDIDATE_TYPE_VOCAB,
                CANDIDATE_TYPE_QUESTION,
                CANDIDATE_TYPE_EXPRESSION,
            },
        ))
        self.assertIn(CANDIDATE_TYPE_VOCAB, types)
        self.assertIn(CANDIDATE_TYPE_QUESTION, types)
        self.assertIn(CANDIDATE_TYPE_EXPRESSION, types)


if __name__ == "__main__":
    unittest.main()
