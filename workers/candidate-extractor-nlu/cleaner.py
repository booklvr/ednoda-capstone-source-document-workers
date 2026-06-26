"""Noise cleaning layer — strips boilerplate and isolated-number lines from extracted plain text."""

from __future__ import annotations

import re
from collections import Counter

# Lines whose first meaningful word(s) are administrative keywords carry no
# educational signal. We also strip lines consisting only of digits/punctuation
# (page numbers, bullet separators, section counters).
_BOILERPLATE_PATTERN = re.compile(
    r"^\s*"
    r"(?:[\d\s./~\-]+\s+)?"          # optional leading number or range  e.g. "41" or "1~2"
    r"(?:"
    r"aims"
    r"|achievement"
    r"|grade(?:\s+\d|\s+level)"       # "Grade 3" / "Grade level" but not stand-alone "grade"
    r"|lesson\s+period"
    r"|learning\s+objectives?"        # "Learning Objectives:" / "Learning Objective"
    r"|check\s+it"
    r"|closing"
    r"|digital\s+multimedia\s+resources"
    r"|chapter(?:\s+\d|\s+\w+:)"      # "Chapter 1:" / "Chapter Two:" but not "chapter" mid-sentence
    r")\b",
    re.IGNORECASE,
)

_NUMBERS_AND_PUNCT_ONLY = re.compile(r"^[\d\s\W]+$")

# Page furniture: "Page 12", "p. 7", "pp. 12-13". These are navigation labels,
# not lesson content. Bare numbers ("12") are already handled by the
# numbers-and-punct-only rule above.
_PAGE_FURNITURE_RE = re.compile(
    r"^\s*(?:page|pp?\.)\s*\d+(?:\s*[-–—]\s*\d+)?\s*$",
    re.IGNORECASE,
)

# Running headers/footers: the same short line repeated on many pages (book
# title, chapter banner) carries no educational signal and inflates candidate
# counts. Thresholds are deliberately conservative so we do not drop legitimate
# repeated lesson content — a real content line rarely repeats verbatim this
# many times.
_MIN_REPEAT_TO_DROP = 4   # must appear at least this many times to be a header
_MAX_HEADER_WORDS = 10    # headers/footers are short; longer repeats are content

# Korean lesson-script speaker tags at the start of a line: "T\t", "S\t", "T ", "S  ".
# A single T or S followed by whitespace is never a real English word start.
_DIALOGUE_MARKER_RE = re.compile(r"^[TS]\s+", re.MULTILINE)

# Mid-sentence line break: a newline immediately preceded by a lowercase letter,
# comma, or hyphen (and NOT followed by another newline — that would be a
# paragraph break we must preserve).
_MID_SENTENCE_BREAK_RE = re.compile(r"(?<=[a-z,\-])\n(?!\n)")


class TextCleaner:
    """Strips noise lines from extracted plain text before NLU chunking."""

    def clean(self, text: str) -> str:
        # 1. Remove Korean lesson-script speaker tags (T\t, S\t, T , S )
        text = _DIALOGUE_MARKER_RE.sub("", text)

        # 2. Identify running headers/footers (document-wide frequency pass).
        running_headers = self._running_header_lines(text)

        # 3. Line-by-line removal of headers, page furniture, standalone
        #    numbers, and boilerplate.
        cleaned: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                cleaned.append("")
                continue
            if stripped in running_headers:
                continue
            if self._is_numbers_and_punct_only(stripped):
                continue
            if self._is_page_furniture(stripped):
                continue
            if self._is_boilerplate(stripped):
                continue
            cleaned.append(line)

        result = "\n".join(cleaned)

        # 3. Stitch mid-sentence line breaks caused by PDF column/page wrapping.
        #    Only single \n after [a-z ,–] is joined; \n\n paragraph breaks are
        #    protected by the negative lookahead.
        result = _MID_SENTENCE_BREAK_RE.sub(" ", result)

        # 4. Collapse runs of 3+ blank lines to 2 so paragraph structure is preserved
        return re.sub(r"\n{3,}", "\n\n", result)

    @staticmethod
    def _running_header_lines(text: str) -> set[str]:
        """Return the set of stripped lines that look like running headers/footers.

        A line qualifies when it is short (header-like) and repeats verbatim at
        least ``_MIN_REPEAT_TO_DROP`` times across the document.
        """
        counts: Counter[str] = Counter()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                counts[stripped] += 1
        return {
            stripped
            for stripped, count in counts.items()
            if count >= _MIN_REPEAT_TO_DROP and len(stripped.split()) <= _MAX_HEADER_WORDS
        }

    @staticmethod
    def _is_page_furniture(line: str) -> bool:
        return bool(_PAGE_FURNITURE_RE.match(line))

    @staticmethod
    def _is_numbers_and_punct_only(line: str) -> bool:
        return bool(_NUMBERS_AND_PUNCT_ONLY.match(line)) and not re.search(r"[a-zA-Z]", line)

    @staticmethod
    def _is_boilerplate(line: str) -> bool:
        return bool(_BOILERPLATE_PATTERN.match(line))
