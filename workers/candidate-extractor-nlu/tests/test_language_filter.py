"""Tests for the target-language gate (Stage A of candidate quality hardening).

See 062526-candidate-quality-language-hardening.md. The gate keeps only
target-language text (default English) and drops other-language content (e.g.
Korean L1 explanation) before BM25/KeyBERT ever see it.
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

from language_filter import filter_to_target_language  # noqa: E402


class FilterToTargetLanguageTests(unittest.TestCase):
    def test_drops_korean_line_keeps_english_lines(self) -> None:
        text = "Hello, how are you?\n안녕하세요 여러분\nWhat is your name?"

        result = filter_to_target_language(text)  # default target = en

        self.assertIn("Hello, how are you?", result)
        self.assertIn("What is your name?", result)
        self.assertNotIn("안녕하세요", result)

    def test_target_language_is_honored_not_hardcoded(self) -> None:
        # The target language is config, not a baked-in constant. With a Korean
        # target the gate must keep Korean and drop English — the inverse of the
        # English default — proving target_language actually drives the decision.
        text = "Hello, how are you?\n안녕하세요 여러분\nWhat is your name?"

        result = filter_to_target_language(text, target_language="ko")

        self.assertIn("안녕하세요 여러분", result)
        self.assertNotIn("Hello, how are you?", result)
        self.assertNotIn("What is your name?", result)

    def test_keeps_english_line_with_small_inline_gloss(self) -> None:
        # Vocabulary lines often carry a short L1 gloss; the predominantly
        # target-language line must survive rather than being dropped wholesale.
        text = "The puppy is a baby dog (강아지)."

        result = filter_to_target_language(text)  # default target = en

        self.assertIn("The puppy is a baby dog", result)

    def test_strips_other_script_tokens_within_a_mixed_line(self) -> None:
        # Real Korean ESL pages interleave scripts on one line; the gate must
        # drop the Korean tokens, not keep the whole line.
        result = filter_to_target_language("robot 로봇 is fun 재미있다")

        self.assertIn("robot", result)
        self.assertIn("is fun", result)
        self.assertFalse(any("가" <= ch <= "힣" for ch in result))


if __name__ == "__main__":
    unittest.main()
