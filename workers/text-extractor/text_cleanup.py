"""Deterministic formatting cleanup for extracted text.

These helpers preserve source meaning. They normalize parser artifacts such as
odd whitespace, bullet glyphs, repeated blank lines, and optional PDF
hyphenation before text is chunked or handed to candidate extraction.
"""

from __future__ import annotations

import re

BULLET_PATTERN = re.compile(r"^\s*[•●○▪▫‣⁃∙]\s*")
HYPHENATED_LINE_BREAK_PATTERN = re.compile(r"(?<=\w)-\n(?=\w)")
PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:\d+|\d+\s*/\s*\d+|(?:page|slide)\s+\d+(?:\s*/\s*\d+)?)$",
    re.IGNORECASE,
)
REPEATED_BLANK_LINES_PATTERN = re.compile(r"\n{3,}")
UNICODE_SPACES = {
    "\u00a0": " ",
    "\u1680": " ",
    "\u2000": " ",
    "\u2001": " ",
    "\u2002": " ",
    "\u2003": " ",
    "\u2004": " ",
    "\u2005": " ",
    "\u2006": " ",
    "\u2007": " ",
    "\u2008": " ",
    "\u2009": " ",
    "\u200a": " ",
    "\u202f": " ",
    "\u205f": " ",
    "\u3000": " ",
}


def normalize_text_block(
    text: str,
    *,
    repair_hyphenation: bool = False,
    drop_page_numbers: bool = False,
) -> str:
    """Clean formatting noise inside one extracted text block."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for source, replacement in UNICODE_SPACES.items():
        normalized = normalized.replace(source, replacement)
    normalized = normalized.replace("\t", "    ")
    normalized = "\n".join(_normalize_line(line) for line in normalized.split("\n"))
    if repair_hyphenation:
        normalized = HYPHENATED_LINE_BREAK_PATTERN.sub("", normalized)
    normalized = REPEATED_BLANK_LINES_PATTERN.sub("\n\n", normalized)
    normalized = "\n".join(
        line
        for line in normalized.split("\n")
        if not _is_drop_line(line, drop_page_numbers=drop_page_numbers)
    )
    return normalized.strip()


def _normalize_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    stripped = BULLET_PATTERN.sub("- ", stripped)
    return re.sub(r" {3,}", "  ", stripped)


def _is_drop_line(line: str, *, drop_page_numbers: bool) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped in {"-", "–", "—", "•"}:
        return True
    return drop_page_numbers and PAGE_NUMBER_PATTERN.match(stripped) is not None
