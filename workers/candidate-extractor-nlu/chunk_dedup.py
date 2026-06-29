"""Cross-chunk overlap de-duplication — Stage B of quality/language hardening.

See 062526-candidate-quality-language-hardening.md.

The sliding-window chunker overlaps adjacent chunks by ~50 words so keyphrases
spanning a boundary still get context. Because the chunker is sentence-aware,
the duplicated unit is a whole sentence shared between neighbouring chunks. Left
as-is, those sentences are scored 2-3x by BM25/KeyBERT, which wastes compute and
inflates BM25 document frequencies (distorting IDF).

This collapses the overlap: each sentence survives in exactly one chunk (the
first chunk it appears in). No coverage loss — every unique sentence is still
present and still scored, just once.

The sentence splitter here only needs to be *consistent across chunks*: adjacent
chunks copy the overlapping sentence verbatim, so splitting both the same way
yields identical fragments that de-duplicate cleanly. It does not need to match
the original chunker's sentencizer exactly.
"""

from __future__ import annotations

import re
from typing import Any

# Split on sentence-ending punctuation followed by whitespace. Deterministic and
# dependency-free; consistency across chunks is what matters (see module docstring).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_SPLIT_RE.split(text.strip()) if part.strip()]


def _normalize(sentence: str) -> str:
    return " ".join(sentence.lower().split())


def dedupe_overlapping_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove sentences already seen in earlier chunks; drop emptied chunks.

    Preserves chunk identity/provenance (``chunkId``, ``index``,
    ``sourceBlockIds``) and recomputes ``text``/``wordCount`` for kept chunks.
    """
    seen: set[str] = set()
    result: list[dict[str, Any]] = []

    for chunk in chunks:
        text = chunk.get("text") or ""
        kept: list[str] = []
        for sentence in _split_sentences(text):
            norm = _normalize(sentence)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            kept.append(sentence)

        new_text = " ".join(kept)
        if not new_text.strip():
            # Fully overlapping chunk: all its content lives in an earlier chunk.
            continue
        result.append({**chunk, "text": new_text, "wordCount": len(new_text.split())})

    return result
