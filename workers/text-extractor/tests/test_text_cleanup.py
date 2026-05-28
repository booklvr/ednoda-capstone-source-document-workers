"""Tests for deterministic text cleanup helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[2]
TEXT_EXTRACTOR_DIR = WORKER_ROOT / "text-extractor"
for path in (WORKER_ROOT, TEXT_EXTRACTOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from text_cleanup import normalize_text_block  # noqa: E402


class TextCleanupTests(unittest.TestCase):
    def test_normalizes_bullets_and_keeps_page_numbers_by_default(self) -> None:
        text = "Page 3\r\n• photo-\r\nsynthesis\r\n\r\n\r\n–\r\n\xa0 chlorophyll"

        cleaned = normalize_text_block(text)

        self.assertIn("Page 3", cleaned)
        self.assertIn("- photo-", cleaned)
        self.assertIn("synthesis", cleaned)
        self.assertIn("chlorophyll", cleaned)
        self.assertNotIn("\r", cleaned)
        self.assertNotIn("\n\n\n", cleaned)

    def test_pdf_options_can_repair_hyphenation_and_drop_page_numbers(self) -> None:
        cleaned = normalize_text_block(
            "Page 3\nphoto-\nsynthesis",
            repair_hyphenation=True,
            drop_page_numbers=True,
        )

        self.assertNotIn("Page 3", cleaned)
        self.assertIn("photosynthesis", cleaned)


if __name__ == "__main__":
    unittest.main()
