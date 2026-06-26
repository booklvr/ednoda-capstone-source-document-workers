"""Tests for the preprocessing composition (Stage A).

See 062526-candidate-quality-language-hardening.md. preprocess_text runs the
target-language gate first (on raw lines, before any line-joining), then the
cleaner, producing target-language-only, de-noised text ready for chunking.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WORKER_ROOT = Path(__file__).resolve().parents[2]
STUB_DIR = WORKER_ROOT / "candidate-extractor-nlu"
for path in (WORKER_ROOT, STUB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from preprocess import preprocess_text, resolve_target_language  # noqa: E402


class PreprocessTextTests(unittest.TestCase):
    def test_drops_other_language_and_noise_keeps_target_content(self) -> None:
        raw = "\n".join(
            [
                "Cool English Book 3",
                "The dog runs fast.",
                "안녕하세요 여러분",
                "Cool English Book 3",
                "She likes apples.",
                "Page 12",
                "Cool English Book 3",
                "We go to school.",
                "Cool English Book 3",
                "Birds can fly.",
                "Cool English Book 3",
            ]
        )

        result = preprocess_text(raw)  # default target = en

        self.assertIn("The dog runs fast.", result)
        self.assertIn("She likes apples.", result)
        self.assertIn("Birds can fly.", result)
        self.assertNotIn("안녕하세요", result)
        self.assertNotIn("Cool English Book 3", result)
        self.assertNotIn("Page 12", result)


class ResolveTargetLanguageTests(unittest.TestCase):
    def test_defaults_to_english_when_env_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_target_language(), "en")

    def test_honors_env_override(self) -> None:
        with patch.dict(os.environ, {"CANDIDATE_TARGET_LANGUAGE": "ko"}, clear=True):
            self.assertEqual(resolve_target_language(), "ko")


if __name__ == "__main__":
    unittest.main()
