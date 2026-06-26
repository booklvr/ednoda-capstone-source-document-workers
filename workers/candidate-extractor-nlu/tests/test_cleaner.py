"""Tests for TextCleaner, including Stage A scraped-data hardening.

See 062526-candidate-quality-language-hardening.md. cleaner.py was previously
untested; the "regression" tests below lock its existing behaviour, and the
"hardening" tests drive the new running-header and page-furniture removal.
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

from cleaner import TextCleaner  # noqa: E402


class CleanerHardeningTests(unittest.TestCase):
    def test_removes_running_header_repeated_across_pages(self) -> None:
        cleaner = TextCleaner()
        header = "Cool English Book 3"
        text = "\n".join(
            [
                header, "The dog runs fast.",
                header, "She likes apples.",
                header, "We go to school.",
                header, "Birds can fly.",
                header, "I have a pen.",
            ]
        )

        result = cleaner.clean(text)

        self.assertNotIn(header, result)
        self.assertIn("The dog runs fast.", result)
        self.assertIn("Birds can fly.", result)

    def test_keeps_line_that_repeats_only_a_few_times(self) -> None:
        # Conservative threshold: a line repeated just twice is NOT treated as a
        # running header — it may be legitimate repeated lesson content.
        cleaner = TextCleaner()
        text = "I like milk.\nWe sing songs.\nI like milk."

        result = cleaner.clean(text)

        self.assertIn("I like milk.", result)
        self.assertIn("We sing songs.", result)

    def test_removes_page_label_lines(self) -> None:
        cleaner = TextCleaner()
        text = "The cat sleeps.\nPage 12\np. 7\npp. 12-13\nThe sun is hot."

        result = cleaner.clean(text)

        self.assertIn("The cat sleeps.", result)
        self.assertIn("The sun is hot.", result)
        self.assertNotIn("Page 12", result)
        self.assertNotIn("p. 7", result)
        self.assertNotIn("pp. 12-13", result)


class CleanerRegressionTests(unittest.TestCase):
    """Lock pre-existing behaviour that the hardening must not break."""

    def test_strips_korean_speaker_tags_keeps_dialogue(self) -> None:
        cleaner = TextCleaner()
        text = "T\tHello class.\nS\tGood morning."

        result = cleaner.clean(text)

        self.assertIn("Hello class.", result)
        self.assertIn("Good morning.", result)
        self.assertNotIn("T\t", result)

    def test_drops_number_only_and_boilerplate_lines(self) -> None:
        cleaner = TextCleaner()
        text = "Learning Objectives: speak\n42\nWe read books."

        result = cleaner.clean(text)

        self.assertNotIn("Learning Objectives", result)
        self.assertNotIn("42", result)
        self.assertIn("We read books.", result)


if __name__ == "__main__":
    unittest.main()
