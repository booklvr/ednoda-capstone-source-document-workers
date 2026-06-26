"""Candidate quality pruning + redundancy reduction — Stage D.

See 062526-candidate-quality-language-hardening.md.

Reduction is earned through *quality*, not an arbitrary cap:
  1. drop low-quality fragments (empty, single-char, numeric-only, lone stopword);
  2. collapse near-duplicates (inflectional + leading-determiner equivalence),
     keeping the highest-confidence survivor;
  3. sort by confidence;
  4. only if a (high, configurable) safety ceiling is exceeded, truncate with a
     round-robin across candidate types so the mix stays balanced (a large
     textbook may legitimately yield many candidates — the ceiling is a guardrail
     to protect teacher review and the Step Functions payload, not the main lever).

Pure and dependency-free so it is fully unit-tested without the NLU stack.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# ENGLISH-DEFAULT: lightweight English stemming + determiners used for
# near-duplicate collapse. For a non-English target these heuristics simply
# collapse fewer items (degrade gracefully); see language_filter.py.
_DETERMINERS = frozenset({"a", "an", "the"})
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "is", "are", "was", "were", "be", "this", "that", "it", "as", "with", "by",
    "from",
})
# Order matters: strip longer/more-specific suffixes first.
_STEM_SUFFIXES = ("ing", "edly", "ied", "ies", "ed", "es", "ly", "s")

# Env knob for the safety ceiling. Default is deliberately high — it is a
# guardrail, not the primary reduction lever. 0 / empty means "no ceiling".
_MAX_RESULTS_ENV_VAR = "CANDIDATE_MAX_RESULTS"
_DEFAULT_MAX_RESULTS = 200


@dataclass
class PruneResult:
    candidates: list[dict[str, Any]]
    stats: dict[str, int]


def resolve_max_candidates() -> int | None:
    """Resolve the safety ceiling from env; None means no ceiling."""
    raw = os.environ.get(_MAX_RESULTS_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_MAX_RESULTS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_RESULTS
    return value if value > 0 else None


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _stem(word: str) -> str:
    for suffix in _STEM_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _is_low_quality(text: str) -> bool:
    norm = _normalize(text)
    if not norm:
        return True
    if len(norm) <= 1:
        return True
    if not any(ch.isalpha() for ch in norm):
        return True
    tokens = norm.split()
    if len(tokens) == 1 and tokens[0] in _STOPWORDS:
        return True
    return False


def _dedup_key(text: str) -> str:
    tokens = _normalize(text).split()
    while tokens and tokens[0] in _DETERMINERS:
        tokens = tokens[1:]
    return " ".join(_stem(token) for token in tokens)


def _confidence(candidate: dict[str, Any]) -> float:
    try:
        return float(candidate.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _balanced_truncate(
    candidates: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Round-robin across candidate types so truncation keeps a balanced mix."""
    by_type: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:  # candidates arrive sorted by confidence desc
        by_type.setdefault(candidate.get("candidateType", "unknown"), []).append(candidate)

    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(by_type.values()):
        for bucket in by_type.values():
            if not bucket:
                continue
            selected.append(bucket.pop(0))
            if len(selected) >= limit:
                break
    return sorted(selected, key=_confidence, reverse=True)


def prune_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_candidates: int | None = _DEFAULT_MAX_RESULTS,
) -> PruneResult:
    input_count = len(candidates)

    # 1. Drop low-quality fragments.
    quality: list[dict[str, Any]] = []
    dropped_low_quality = 0
    for candidate in candidates:
        if _is_low_quality(candidate.get("text", "") or ""):
            dropped_low_quality += 1
            continue
        quality.append(candidate)

    # 2. Collapse near-duplicates, keeping the highest-confidence survivor.
    best_by_key: dict[str, dict[str, Any]] = {}
    for candidate in quality:
        key = _dedup_key(candidate.get("text", "") or "")
        existing = best_by_key.get(key)
        if existing is None or _confidence(candidate) > _confidence(existing):
            best_by_key[key] = candidate
    collapsed = sorted(best_by_key.values(), key=_confidence, reverse=True)
    collapsed_duplicates = len(quality) - len(collapsed)

    # 3 + 4. Apply the safety ceiling only when exceeded.
    ceiling_applied = 0
    if max_candidates is not None and len(collapsed) > max_candidates:
        result = _balanced_truncate(collapsed, max_candidates)
        ceiling_applied = 1
    else:
        result = collapsed

    stats = {
        "input": input_count,
        "droppedLowQuality": dropped_low_quality,
        "collapsedDuplicates": collapsed_duplicates,
        "ceilingApplied": ceiling_applied,
        "output": len(result),
    }
    return PruneResult(candidates=result, stats=stats)
