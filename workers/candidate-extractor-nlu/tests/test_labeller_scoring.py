"""Tests for Stage C scoring-hardening helpers in labeller.py.

See 062526-candidate-quality-language-hardening.md. These pure helpers are the
testable core of: (C1) skipping empty/garbage BM25 queries, (C2) merging batched
KeyBERT results, and (C3) the belt-and-suspenders target-language check at
candidate emission. The model calls themselves require bm25s/keybert and are
verified in staging.
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

from labeller import (  # noqa: E402
    _has_scorable_tokens,
    _is_target_language_phrase,
    _merge_keyphrase_scores,
)


class HasScorableTokensTests(unittest.TestCase):
    def test_true_for_real_content(self) -> None:
        self.assertTrue(_has_scorable_tokens("The cat sleeps."))

    def test_false_for_numbers_and_punctuation_only(self) -> None:
        self.assertFalse(_has_scorable_tokens("12 34 ---"))

    def test_false_for_all_stopwords(self) -> None:
        # "the the the" tokenizes to nothing after stopword removal -> the empty
        # query that produces the BM25 log spam. Skip it.
        self.assertFalse(_has_scorable_tokens("the the the"))

    def test_false_for_empty(self) -> None:
        self.assertFalse(_has_scorable_tokens("   "))


class MergeKeyphraseScoresTests(unittest.TestCase):
    def test_keeps_max_score_per_phrase_and_skips_empty(self) -> None:
        keyword_lists = [
            [("cat", 0.5), ("dog", 0.3)],
            [("cat", 0.8), ("", 0.9)],
        ]

        merged = _merge_keyphrase_scores(keyword_lists)

        self.assertEqual(merged["cat"], 0.8)
        self.assertEqual(merged["dog"], 0.3)
        self.assertNotIn("", merged)


class IsTargetLanguagePhraseTests(unittest.TestCase):
    def test_english_phrase_is_target_by_default(self) -> None:
        self.assertTrue(_is_target_language_phrase("dog", "en"))

    def test_korean_phrase_is_not_english_target(self) -> None:
        self.assertFalse(_is_target_language_phrase("안녕하세요", "en"))

    def test_korean_phrase_is_target_when_target_is_korean(self) -> None:
        self.assertTrue(_is_target_language_phrase("안녕하세요", "ko"))

    def test_mixed_script_phrase_is_rejected_for_english(self) -> None:
        # A keyphrase mixing scripts (e.g. "robot 로봇") must be rejected for an
        # English target — this was leaking on real bilingual pages.
        self.assertFalse(_is_target_language_phrase("robot 로봇", "en"))


if __name__ == "__main__":
    unittest.main()
