"""Deterministic Alpha candidate heuristics over extracted plain text."""

from __future__ import annotations

import re
from collections import Counter
from math import ceil
from typing import Any, TypedDict

from shared.contracts import (
    CANDIDATE_TYPE_EXPRESSION,
    CANDIDATE_TYPE_QUESTION,
    CANDIDATE_TYPE_VOCAB,
   )

# Lines longer than this are treated as noisy document body, not review candidates.
MAX_LINE_LENGTH = 500
MIN_LINE_LENGTH = 2

# Expression heuristic: short phrases repeated across lines.
MAX_EXPRESSION_PHRASE_LENGTH = 60
MIN_EXPRESSION_WORDS = 2
MAX_EXPRESSION_WORDS = 5
MIN_EXPRESSION_REPETITIONS = 2

VOCABULARY_LINE_PATTERNS = (
    re.compile(r"^(.+?)\s*:\s+(.+)$"),
    re.compile(r"^(.+?)\s+-\s+(.+)$"),
    re.compile(r"^(.+?)\s+—\s+(.+)$"),
)

NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")
PAGE_OR_SLIDE_PATTERN = re.compile(
    r"^(?:\d+|\d+\s*/\s*\d+|(?:page|slide)\s+\d+(?:\s*/\s*\d+)?)$",
    re.IGNORECASE,
)
BOILERPLATE_PATTERN = re.compile(
    r"\b(?:all rights reserved|copyright|©|confidential|do not distribute)\b",
    re.IGNORECASE,
)


class CandidateDraft(TypedDict, total=False):
    candidateType: str
    text: str
    normalizedText: str
    sourceBlockId: str | None
    sourcePageNumber: int | None
    confidence: float
    metadata: dict[str, Any]


def normalize_candidate_text(text: str) -> str:
    """Lowercase, collapse whitespace, and strip punctuation for dedupe keys."""
    collapsed = " ".join(text.strip().lower().split())
    return NON_ALNUM_PATTERN.sub(" ", collapsed).strip()


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < MIN_LINE_LENGTH:
        return True
    if len(stripped) > MAX_LINE_LENGTH:
        return True
    if not re.search(r"[a-zA-Z0-9]", stripped):
        return True
    if stripped in {"-", "–", "—", "•"}:
        return True
    if PAGE_OR_SLIDE_PATTERN.match(stripped):
        return True
    if BOILERPLATE_PATTERN.search(stripped):
        return True
    return False


def _match_vocabulary_line(line: str) -> str | None:
    for pattern in VOCABULARY_LINE_PATTERNS:
        match = pattern.match(line.strip())
        if not match:
            continue
        term = match.group(1).strip()
        definition = match.group(2).strip()
        if len(term) < 1 or len(definition) < 1:
            continue
        if len(term) > 120 or len(definition) > 400:
            continue
        return line.strip()
    return None


def _line_block_id(line_number: int) -> str:
    return f"line-{line_number:06d}"


def classify_line_candidate(line: str, line_number: int) -> CandidateDraft | None:
    """Classify a single non-noise line as question or vocabulary."""
    stripped = line.strip()
    if _is_noise_line(stripped):
        return None

    block_id = _line_block_id(line_number)
    metadata = {
        "heuristic": "alpha_line_classifier",
        "sourceLine": line_number,
        "sourceLineText": stripped,
    }

    if "?" in stripped:
        normalized = normalize_candidate_text(stripped)
        return {
            "candidateType": CANDIDATE_TYPE_QUESTION,
            "text": stripped,
            "normalizedText": normalized,
            "sourceBlockId": block_id,
            "confidence": 0.8,
            "metadata": metadata,
        }

    vocabulary_text = _match_vocabulary_line(stripped)
    if vocabulary_text:
        normalized = normalize_candidate_text(vocabulary_text)
        return {
            "candidateType": CANDIDATE_TYPE_VOCAB,
            "text": vocabulary_text,
            "normalizedText": normalized,
            "sourceBlockId": block_id,
            "confidence": 0.75,
            "metadata": {**metadata, "heuristic": "alpha_vocabulary_pattern"},
        }

    return None


def _expression_phrase_candidates(line: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9']+", line.lower())
    phrases: list[str] = []
    for window in range(MIN_EXPRESSION_WORDS, MAX_EXPRESSION_WORDS + 1):
        if len(words) < window:
            continue
        for index in range(0, len(words) - window + 1):
            phrase = " ".join(words[index : index + window])
            if len(phrase) < 4 or len(phrase) > MAX_EXPRESSION_PHRASE_LENGTH:
                continue
            phrases.append(phrase)
    return phrases


def detect_expression_candidates(lines: list[str]) -> list[CandidateDraft]:
    """Find short phrases that repeat on multiple non-noise lines."""
    phrase_counts: Counter[str] = Counter()
    phrase_line_numbers: dict[str, list[int]] = {}

    for line_number, line in enumerate(lines, start=1):
        if _is_noise_line(line):
            continue
        seen_in_line: set[str] = set()
        for phrase in _expression_phrase_candidates(line):
            if phrase in seen_in_line:
                continue
            seen_in_line.add(phrase)
            phrase_counts[phrase] += 1
            phrase_line_numbers.setdefault(phrase, []).append(line_number)

    candidates: list[CandidateDraft] = []
    for phrase, count in phrase_counts.items():
        if count < MIN_EXPRESSION_REPETITIONS:
            continue
        line_numbers = phrase_line_numbers[phrase]
        first_line = line_numbers[0]
        display = phrase
        candidates.append(
            {
                "candidateType": CANDIDATE_TYPE_EXPRESSION,
                "text": display,
                "normalizedText": normalize_candidate_text(display),
                "sourceBlockId": _line_block_id(first_line),
                "confidence": 0.65,
                "metadata": {
                    "heuristic": "alpha_repeated_phrase",
                    "repetitionCount": count,
                    "sourceLines": line_numbers,
                },
            },
        )
    return candidates


def dedupe_candidates(candidates: list[CandidateDraft]) -> list[CandidateDraft]:
    """Drop duplicates by candidate type and normalized text (or raw text)."""
    seen: set[tuple[str, str]] = set()
    deduped: list[CandidateDraft] = []

    for candidate in candidates:
        candidate_type = candidate["candidateType"]
        normalized = candidate.get("normalizedText") or normalize_candidate_text(
            candidate["text"],
        )
        key = (candidate_type, normalized)
        if key in seen:
            continue
        seen.add(key)
        candidate["normalizedText"] = normalized
        deduped.append(candidate)

    return deduped


def _filter_repeated_noise_lines(lines: list[str]) -> list[str]:
    if len(lines) < 3:
        return lines

    counts: Counter[str] = Counter()
    for line in lines:
        stripped = line.strip()
        if _is_noise_line(stripped) or len(stripped) > 90:
            continue
        if ":" in stripped or "?" in stripped:
            continue
        counts[normalize_candidate_text(stripped)] += 1

    threshold = max(3, ceil(len(lines) * 0.4))
    repeated = {line for line, count in counts.items() if count >= threshold}
    if not repeated:
        return lines

    return [
        line
        for line in lines
        if normalize_candidate_text(line) not in repeated
    ]


def extract_candidates_from_plain_text(plain_text: str) -> list[CandidateDraft]:
    """Run Alpha heuristics over plain.txt content."""
    lines = _filter_repeated_noise_lines(plain_text.splitlines())
    candidates: list[CandidateDraft] = []

    for line_number, line in enumerate(lines, start=1):
        line_candidate = classify_line_candidate(line, line_number)
        if line_candidate:
            candidates.append(line_candidate)

    candidates.extend(detect_expression_candidates(lines))
    return dedupe_candidates(candidates)
