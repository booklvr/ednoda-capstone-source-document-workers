"""BM25S + KeyBERT + spaCy ensemble labeller for candidate extraction."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

try:
    import bm25s as _bm25s_lib
except ImportError:
    _bm25s_lib = None
    print("WARNING: bm25s not available; NLULabeller will use KeyBERT only")

try:
    from keybert import KeyBERT as _KeyBERT
except ImportError:
    _KeyBERT = None
    print("WARNING: keybert not available; NLULabeller will return question candidates only")

try:
    import spacy as _spacy_lib
except ImportError:
    _spacy_lib = None
    print("WARNING: spacy not available; NLULabeller question detection and sentence splitting disabled")

_WORKER_ROOT = Path(__file__).resolve().parents[1]
_STUB_DIR = Path(__file__).resolve().parent
for _path in (_WORKER_ROOT, _STUB_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

try:
    from shared.contracts import (
        CANDIDATE_TYPE_EXPRESSION,
        CANDIDATE_TYPE_QUESTION,
        CANDIDATE_TYPE_VOCAB,
    )
except ImportError:
    CANDIDATE_TYPE_VOCAB = "vocab"
    CANDIDATE_TYPE_EXPRESSION = "expression"
    CANDIDATE_TYPE_QUESTION = "question"

CANDIDATE_TYPE_UNKNOWN = "unknown"

QUESTION_STARTERS = frozenset({
    "what", "where", "when", "who", "why", "how", "which", "whose", "whom",
})

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name, "").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name, "").strip()
    if not val:
        return default
    try:
        return max(1, int(val))
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    val = os.environ.get(name, "").strip()
    return val if val else default


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _strip_punct(word: str) -> str:
    return word.strip(".,;:!?\"'()-–—")


class NLULabeller:
    """Ensemble labeller: BM25S + KeyBERT scoring with spaCy question detection."""

    def __init__(
        self,
        keybert_model: str = "all-MiniLM-L6-v2",
        bm25s_top_n: int = 20,
        keybert_top_n: int = 20,
        keybert_threshold: float = 0.55,
        agreement_confidence: float = 0.91,
        fallback_confidence: float = 0.72,
        question_confidence: float = 0.60,
    ) -> None:
        self.keybert_model = _env_str("KEYBERT_MODEL", keybert_model)
        self.bm25s_top_n = _env_int("BM25S_TOP_N", bm25s_top_n)
        self.keybert_top_n = _env_int("KEYBERT_TOP_N", keybert_top_n)
        self.keybert_threshold = _env_float("KEYBERT_THRESHOLD", keybert_threshold)
        self.agreement_confidence = _env_float("AGREEMENT_CONFIDENCE", agreement_confidence)
        self.fallback_confidence = _env_float("FALLBACK_CONFIDENCE", fallback_confidence)
        self.question_confidence = _env_float("QUESTION_CONFIDENCE", question_confidence)

        self._kw_model: Any = None
        self._kw_loaded = False
        self._nlp: Any = None
        self._nlp_loaded = False

    # ------------------------------------------------------------------
    # Internal: model loading
    # ------------------------------------------------------------------

    def _load_keybert(self) -> Any:
        if self._kw_loaded:
            return self._kw_model
        self._kw_loaded = True
        if _KeyBERT is None:
            return None
        try:
            self._kw_model = _KeyBERT(self.keybert_model)
        except Exception as exc:
            logger.warning("KeyBERT model failed to load (%s): %s", self.keybert_model, exc)
        return self._kw_model

    def _load_nlp(self) -> Any:
        if self._nlp_loaded:
            return self._nlp
        self._nlp_loaded = True
        if _spacy_lib is None:
            return None
        try:
            # Try a full model first for POS tagging; fall back to blank + sentencizer
            try:
                self._nlp = _spacy_lib.load("en_core_web_sm")
            except OSError:
                nlp = _spacy_lib.blank("en")
                nlp.add_pipe("sentencizer")
                self._nlp = nlp
        except Exception as exc:
            logger.warning("spaCy NLP failed to load: %s", exc)
        return self._nlp

    # ------------------------------------------------------------------
    # Internal: BM25S scoring
    # ------------------------------------------------------------------

    def _score_bm25s(self, chunks: list[dict]) -> dict[str, float]:
        """Build a BM25S index, query each chunk against the corpus, return word -> score (0-1)."""
        if _bm25s_lib is None:
            return {}
        if len(chunks) < 2:
            logger.warning(
                "BM25S requires multiple chunks to score meaningfully; got %d chunk(s)", len(chunks)
            )
            return {}
        try:
            texts = [chunk.get("text", "") for chunk in chunks]
            corpus_tokens = _bm25s_lib.tokenize(texts, stopwords="en")
            retriever = _bm25s_lib.BM25()
            retriever.index(corpus_tokens)

            n_docs = len(texts)
            k = min(n_docs, self.bm25s_top_n)
            term_scores: dict[str, float] = {}

            for chunk in chunks:
                text = chunk.get("text", "")
                if not text.strip():
                    continue
                try:
                    q_tokens = _bm25s_lib.tokenize([text], stopwords="en")
                    results, scores = retriever.retrieve(q_tokens, k=k)
                    for i in range(len(results[0])):
                        doc_idx = int(results[0][i])
                        doc_score = float(scores[0][i])
                        if doc_idx < 0 or doc_idx >= n_docs:
                            continue
                        for raw_word in texts[doc_idx].split():
                            word = _strip_punct(raw_word.lower())
                            if len(word) <= 1:
                                continue
                            if doc_score > term_scores.get(word, 0.0):
                                term_scores[word] = doc_score
                except Exception as exc:
                    logger.warning("BM25S chunk query failed: %s", exc)
                    continue

            if not term_scores:
                return {}

            vals = list(term_scores.values())
            min_val = min(vals)
            max_val = max(vals)
            if max_val <= 0 or max_val == min_val:
                return {k: 1.0 for k in term_scores}
            return {
                k: (v - min_val) / (max_val - min_val)
                for k, v in term_scores.items()
            }
        except Exception as exc:
            logger.warning("BM25S scoring failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Internal: KeyBERT scoring
    # ------------------------------------------------------------------

    def _score_keybert(self, chunks: list[dict]) -> dict[str, float]:
        """Run KeyBERT on each chunk; return keyphrase -> max score across all chunks."""
        kw_model = self._load_keybert()
        if kw_model is None:
            return {}
        try:
            phrase_scores: dict[str, float] = {}
            for chunk in chunks:
                text = chunk.get("text", "") or ""
                if not text.strip():
                    continue
                try:
                    keywords = kw_model.extract_keywords(
                        text,
                        keyphrase_ngram_range=(1, 3),
                        top_n=self.keybert_top_n,
                        stop_words="english",
                    )
                    for phrase, score in keywords:
                        key = phrase.lower().strip()
                        if not key:
                            continue
                        if key not in phrase_scores or float(score) > phrase_scores[key]:
                            phrase_scores[key] = float(score)
                except Exception as exc:
                    logger.warning("KeyBERT extraction failed on chunk: %s", exc)
                    continue
            return phrase_scores
        except Exception as exc:
            logger.warning("KeyBERT scoring failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Internal: question detection
    # ------------------------------------------------------------------

    def _detect_questions(self, blocks: list[dict]) -> list[dict]:
        """Detect interrogative sentences in blocks using spaCy sentence detection and POS tags."""
        nlp = self._load_nlp()
        has_tagger = (
            nlp is not None
            and any(p in nlp.pipe_names for p in ("tagger", "morphologizer", "tok2vec"))
        )
        candidates: list[dict] = []

        for block in blocks:
            block_text = block.get("text") or ""
            if not block_text.strip():
                continue

            block_id = block.get("blockId") or block.get("id")
            source = block.get("source") if isinstance(block.get("source"), dict) else {}
            page_number = source.get("pageNumber")
            slide_number = source.get("slideNumber")

            sentences: list[str] = []
            if nlp is not None:
                try:
                    doc = nlp(block_text)
                    sentences = [s.text.strip() for s in doc.sents if s.text.strip()]
                except Exception:
                    sentences = [s.strip() for s in block_text.split(". ") if s.strip()]
            else:
                sentences = [s.strip() for s in block_text.split(". ") if s.strip()]

            for sentence in sentences:
                if not sentence:
                    continue

                is_question = False

                if sentence.endswith("?"):
                    is_question = True
                else:
                    words = sentence.split()
                    if words:
                        first_word = _strip_punct(words[0].lower())
                        if first_word in QUESTION_STARTERS:
                            if has_tagger and nlp is not None:
                                try:
                                    sent_doc = nlp(sentence)
                                    is_question = any(
                                        tok.pos_ in {"VERB", "AUX"} for tok in sent_doc
                                    )
                                except Exception:
                                    is_question = True
                            else:
                                # No POS tagger available; accept question word alone as signal
                                is_question = True

                if is_question:
                    candidates.append({
                        "candidateType": CANDIDATE_TYPE_QUESTION,
                        "text": sentence,
                        "normalizedText": _normalize_text(sentence),
                        "sourceBlockId": str(block_id) if block_id is not None else None,
                        "sourcePageNumber": page_number,
                        "sourceSlideNumber": slide_number,
                        "confidence": self.question_confidence,
                        "metadata": {"engine": "spacy_pattern"},
                    })

        return candidates

    # ------------------------------------------------------------------
    # Internal: source block lookup for keyphrase candidates
    # ------------------------------------------------------------------

    def _find_source_block(
        self,
        keyphrase: str,
        chunks: list[dict],
        blocks: list[dict],
    ) -> tuple[str | None, int | None, int | None]:
        """Return (blockId, pageNumber, slideNumber) for the first chunk containing keyphrase."""
        phrase_lower = keyphrase.lower()
        for chunk in chunks:
            chunk_text = (chunk.get("text") or "").lower()
            if phrase_lower not in chunk_text:
                continue
            block_ids = chunk.get("sourceBlockIds") or []
            if not block_ids:
                continue
            block_id = block_ids[0]
            for block in blocks:
                bid = block.get("blockId") or block.get("id")
                if bid is not None and str(bid) == str(block_id):
                    source = block.get("source") if isinstance(block.get("source"), dict) else {}
                    return (
                        str(block_id),
                        source.get("pageNumber"),
                        source.get("slideNumber"),
                    )
            return str(block_id), None, None
        return None, None, None

    # ------------------------------------------------------------------
    # Public: label
    # ------------------------------------------------------------------

    def label(self, chunks: list[dict], blocks: list[dict]) -> list[dict]:
        try:
            return self._label(chunks, blocks)
        except Exception as exc:
            logger.warning("NLULabeller.label failed: %s", exc)
            return []

    def _label(self, chunks: list[dict], blocks: list[dict]) -> list[dict]:
        candidates: list[dict] = []

        # 1. BM25S scores
        bm25s_scores: dict[str, float] = {}
        bm25s_failed = False
        try:
            bm25s_scores = self._score_bm25s(chunks)
        except Exception as exc:
            logger.warning("BM25S scoring failed, falling back to KeyBERT only: %s", exc)
            bm25s_failed = True

        bm25s_available = bool(bm25s_scores) and not bm25s_failed
        bm25s_top_set: set[str] = set(
            sorted(bm25s_scores, key=bm25s_scores.__getitem__, reverse=True)[: self.bm25s_top_n]
        )

        # 2. KeyBERT scores
        keybert_scores: dict[str, float] = {}
        keybert_failed = False
        try:
            keybert_scores = self._score_keybert(chunks)
            if not keybert_scores and _KeyBERT is not None:
                keybert_failed = True
        except Exception as exc:
            logger.warning("KeyBERT scoring failed: %s", exc)
            keybert_failed = True

        keybert_top_set: set[str] = set(
            sorted(keybert_scores, key=keybert_scores.__getitem__, reverse=True)[: self.keybert_top_n]
        )

        # 3. Ensemble: vocab / expression candidates from KeyBERT
        if not keybert_failed:
            for keyphrase, kb_score in keybert_scores.items():
                token_count = len(keyphrase.split())

                if token_count == 1:
                    candidate_type = CANDIDATE_TYPE_VOCAB
                elif token_count <= 3:
                    candidate_type = CANDIDATE_TYPE_EXPRESSION
                else:
                    continue

                in_bm25s_top = keyphrase in bm25s_top_set
                in_keybert_top = keyphrase in keybert_top_set

                if bm25s_available and in_bm25s_top and in_keybert_top:
                    tier = "agreement"
                    confidence = self.agreement_confidence
                elif in_keybert_top and kb_score > self.keybert_threshold:
                    tier = "fallback"
                    confidence = self.fallback_confidence
                else:
                    continue

                source_block_id, page_number, slide_number = self._find_source_block(
                    keyphrase, chunks, blocks
                )

                candidates.append({
                    "candidateType": candidate_type,
                    "text": keyphrase,
                    "normalizedText": _normalize_text(keyphrase),
                    "sourceBlockId": source_block_id,
                    "sourcePageNumber": page_number,
                    "sourceSlideNumber": slide_number,
                    "confidence": confidence,
                    "metadata": {
                        "engine": tier,
                        "keybert_score": kb_score,
                        "bm25s_score": bm25s_scores.get(keyphrase),
                    },
                })

        # 4. Question detection (runs regardless of KeyBERT/BM25S status)
        try:
            candidates.extend(self._detect_questions(blocks))
        except Exception as exc:
            logger.warning("Question detection failed: %s", exc)

        # 5. Deduplicate by normalizedText, keeping highest confidence
        seen: dict[str, dict] = {}
        for cand in candidates:
            key = cand["normalizedText"]
            if key not in seen or cand["confidence"] > seen[key]["confidence"]:
                seen[key] = cand

        # 6. Sort by confidence descending
        return sorted(seen.values(), key=lambda c: c["confidence"], reverse=True)
