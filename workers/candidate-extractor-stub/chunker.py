"""Sliding-window sentence-aware chunker over extracted text packages."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

try:
    import spacy as _spacy_lib
except ImportError:
    _spacy_lib = None
    print("WARNING: spacy not available; SlidingWindowChunker falls back to '. ' sentence splitting")

_WORKER_ROOT = Path(__file__).resolve().parents[1]
_STUB_DIR = Path(__file__).resolve().parent
for _path in (_WORKER_ROOT, _STUB_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

logger = logging.getLogger(__name__)


class SlidingWindowChunker:
    """Splits plain text into overlapping word-count-bounded chunks, respecting sentence boundaries."""

    def __init__(self, chunk_size: int = 200, overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._nlp: Any = None
        self._nlp_attempted = False

    def _load_nlp(self) -> Any:
        if self._nlp_attempted:
            return self._nlp
        self._nlp_attempted = True
        if _spacy_lib is None:
            return None
        try:
            nlp = _spacy_lib.blank("en")
            nlp.add_pipe("sentencizer")
            self._nlp = nlp
        except Exception as exc:
            logger.warning("spacy sentencizer failed to load: %s", exc)
        return self._nlp

    def _split_sentences(self, text: str) -> list[str]:
        nlp = self._load_nlp()
        if nlp is not None:
            try:
                doc = nlp(text)
                return [s.text.strip() for s in doc.sents if s.text.strip()]
            except Exception as exc:
                logger.warning("spacy sentence split failed, using fallback: %s", exc)
        # Fallback: split on ". "
        parts = text.split(". ")
        sentences: list[str] = []
        for idx, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            if idx < len(parts) - 1:
                sentences.append(part + ".")
            else:
                sentences.append(part)
        return sentences

    def _collect_block_ids(self, sentences: list[str], blocks: list[dict]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for sentence in sentences:
            for block in blocks:
                block_text = block.get("text") or ""
                if sentence in block_text:
                    block_id = block.get("blockId") or block.get("id")
                    if block_id is not None:
                        bid = str(block_id)
                        if bid not in seen:
                            seen.add(bid)
                            result.append(bid)
        return result

    def chunk(self, plain_text: str, blocks: list[dict]) -> list[dict]:
        try:
            return self._chunk(plain_text, blocks)
        except Exception as exc:
            logger.warning("SlidingWindowChunker.chunk failed: %s", exc)
            return []

    def _chunk(self, plain_text: str, blocks: list[dict]) -> list[dict]:
        if not plain_text or not plain_text.strip():
            return []

        sentences = self._split_sentences(plain_text)
        if not sentences:
            return []

        chunks: list[dict] = []
        chunk_index = 0
        start_idx = 0

        while start_idx < len(sentences):
            current_sentences: list[str] = []
            current_word_count = 0
            idx = start_idx

            while idx < len(sentences):
                sentence = sentences[idx]
                word_count = len(sentence.split())
                if current_word_count > 0 and current_word_count + word_count > self.chunk_size:
                    break
                current_sentences.append(sentence)
                current_word_count += word_count
                idx += 1
                if current_word_count >= self.chunk_size:
                    break

            if not current_sentences:
                break

            chunk_id = f"chunk-{(chunk_index + 1):06d}"
            chunks.append({
                "chunkId": chunk_id,
                "index": chunk_index,
                "text": " ".join(current_sentences),
                "wordCount": current_word_count,
                "sourceBlockIds": self._collect_block_ids(current_sentences, blocks),
            })
            chunk_index += 1

            if idx >= len(sentences):
                break

            # Step back to create overlap: find how many trailing sentences cover `overlap` words
            if self.overlap > 0:
                overlap_words = 0
                overlap_sents = 0
                for sent in reversed(current_sentences):
                    if overlap_words >= self.overlap:
                        break
                    overlap_words += len(sent.split())
                    overlap_sents += 1
                # Must advance by at least 1 sentence to avoid an infinite loop
                next_start = max(start_idx + 1, idx - overlap_sents)
            else:
                next_start = idx

            start_idx = next_start

        return chunks
