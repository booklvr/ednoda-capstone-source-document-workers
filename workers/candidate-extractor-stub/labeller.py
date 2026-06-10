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

# "grammar" is not in shared/contracts.py — defined locally here.
# When Nick adds it to the shared contract, replace with the import.
CANDIDATE_TYPE_GRAMMAR = "grammar"

_GRAMMAR_CONFIDENCE = 0.80
_LEXICAL_ANCHOR_CONFIDENCE = 0.95
# Anchor words are no longer hardcoded here. Pass them via NLULabeller(anchor_words=...)
# so the caller (local_evaluator, Lambda handler, or tests) controls the word list.

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
        anchor_words: frozenset[str] | None = None,
    ) -> None:
        self.keybert_model = _env_str("KEYBERT_MODEL", keybert_model)
        self.bm25s_top_n = _env_int("BM25S_TOP_N", bm25s_top_n)
        self.keybert_top_n = _env_int("KEYBERT_TOP_N", keybert_top_n)
        self.keybert_threshold = _env_float("KEYBERT_THRESHOLD", keybert_threshold)
        self.agreement_confidence = _env_float("AGREEMENT_CONFIDENCE", agreement_confidence)
        self.fallback_confidence = _env_float("FALLBACK_CONFIDENCE", fallback_confidence)
        self.question_confidence = _env_float("QUESTION_CONFIDENCE", question_confidence)
        self._anchor_words: frozenset[str] = anchor_words if anchor_words is not None else frozenset()

        self._kw_model: Any = None
        self._kw_loaded = False
        self._nlp: Any = None
        self._nlp_loaded = False
        self._grammar_matcher: Any = None
        self._grammar_matcher_loaded = False

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
    # Internal: imperative detection (teacher-instruction filter)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_imperative(sent: Any) -> bool:
        """True if the sentence is likely a teacher instruction in imperative mood.

        Heuristic: the syntactic ROOT is a bare-form verb (Penn tag VB) and it
        has no nominal subject (nsubj / nsubjpass) child.

        Examples caught:  "Read the passage."  "Ask your partner."  "Write the answer."
        Examples kept:    "She is reading."    "They asked a question."

        Dialogue guard: any sentence containing quotation marks (" " ") is
        immediately treated as narrative speech, not a teacher instruction, and
        returns False — protecting lines like: Grace yelled, "Hold fast!"
        """
        text = sent.text if hasattr(sent, "text") else str(sent)
        if any(q in text for q in ('"', '“', '”')):
            return False

        for token in sent:
            if token.dep_ == "ROOT":
                if token.tag_ == "VB" and not any(
                    child.dep_ in ("nsubj", "nsubjpass") for child in token.children
                ):
                    return True
                break
        return False

    # ------------------------------------------------------------------
    # Internal: grammar pattern detection (DependencyMatcher)
    # ------------------------------------------------------------------

    def _load_grammar_matcher(self) -> Any:
        if self._grammar_matcher_loaded:
            return self._grammar_matcher
        self._grammar_matcher_loaded = True
        nlp = self._load_nlp()
        if nlp is None:
            return None
        if "parser" not in nlp.pipe_names:
            logger.warning("Grammar matcher requires a dependency parser; not available in loaded spaCy model")
            return None
        try:
            from spacy.matcher import DependencyMatcher
            matcher = DependencyMatcher(nlp.vocab)

            # ---- Original 4 templates ----

            # 1. Present Simple Question with do/does  e.g. "Do you like pizza?"
            matcher.add("present_simple_question", [[
                {"RIGHT_ID": "root_node", "RIGHT_ATTRS": {}},
                {"LEFT_ID": "root_node", "REL_OP": ">", "RIGHT_ID": "aux_do",
                 "RIGHT_ATTRS": {"LOWER": {"IN": ["do", "does"]}, "DEP": "aux"}},
                {"LEFT_ID": "root_node", "REL_OP": ">", "RIGHT_ID": "punct",
                 "RIGHT_ATTRS": {"ORTH": "?"}},
            ]])

            # 2. There is/are ___  e.g. "There is a dog."
            matcher.add("there_is_are", [[
                {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be"}},
                {"LEFT_ID": "be_verb", "REL_OP": ">", "RIGHT_ID": "there_expl",
                 "RIGHT_ATTRS": {"LOWER": "there", "DEP": "expl"}},
            ]])

            # 3. Comparative ___ is -er than ___  e.g. "A lion is bigger than a dog."
            matcher.add("comparative", [[
                {"RIGHT_ID": "adj_comp", "RIGHT_ATTRS": {"TAG": "JJR"}},
                {"LEFT_ID": "adj_comp", "REL_OP": ">", "RIGHT_ID": "than",
                 "RIGHT_ATTRS": {"LOWER": "than", "DEP": "prep"}},
            ]])

            # 4. Present Continuous  e.g. "She is listening to music."
            matcher.add("present_continuous", [[
                {"RIGHT_ID": "verb_ing", "RIGHT_ATTRS": {"TAG": "VBG"}},
                {"LEFT_ID": "verb_ing", "REL_OP": ">", "RIGHT_ID": "aux_be",
                 "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "aux"}},
            ]])

            # ---- Frequency-ordered ESL templates ----

            # 5. Be + attribute noun  e.g. "My name is Tom."
            matcher.add("be_attr_statement", [[
                {"RIGHT_ID": "be_root", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
                {"LEFT_ID": "be_root", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "be_root", "REL_OP": ">", "RIGHT_ID": "attr_noun",
                 "RIGHT_ATTRS": {"DEP": "attr"}},
            ]])

            # 6. Be + adjective  e.g. "The bus is big."
            matcher.add("be_adjective", [[
                {"RIGHT_ID": "be_root", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
                {"LEFT_ID": "be_root", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "be_root", "REL_OP": ">", "RIGHT_ID": "adj_comp",
                 "RIGHT_ATTRS": {"DEP": "acomp"}},
            ]])

            # 7. Can question  e.g. "Can you help me?"
            matcher.add("can_question", [[
                {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"DEP": "ROOT", "POS": "VERB"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "modal_can",
                 "RIGHT_ATTRS": {"LOWER": "can", "DEP": "aux"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "quest_mark",
                 "RIGHT_ATTRS": {"ORTH": "?"}},
            ]])

            # 8. Like statement  e.g. "I like milk."
            matcher.add("like_statement", [[
                {"RIGHT_ID": "like_verb", "RIGHT_ATTRS": {"LEMMA": "like", "DEP": "ROOT"}},
                {"LEFT_ID": "like_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "like_verb", "REL_OP": ">", "RIGHT_ID": "obj",
                 "RIGHT_ATTRS": {"DEP": "dobj"}},
            ]])

            # 9. Be from place  e.g. "I am from Canada."
            matcher.add("be_from_place", [[
                {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
                {"LEFT_ID": "be_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "be_verb", "REL_OP": ">", "RIGHT_ID": "from_prep",
                 "RIGHT_ATTRS": {"LOWER": "from", "DEP": "prep"}},
            ]])

            # 10. Have statement  e.g. "I have scissors."
            matcher.add("have_statement", [[
                {"RIGHT_ID": "have_verb", "RIGHT_ATTRS": {"LEMMA": "have", "DEP": "ROOT"}},
                {"LEFT_ID": "have_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "have_verb", "REL_OP": ">", "RIGHT_ID": "obj",
                 "RIGHT_ATTRS": {"DEP": "dobj"}},
            ]])

            # 11. Wh-question with be  e.g. "How are you?"
            matcher.add("wh_question_be", [[
                {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
                {"LEFT_ID": "be_verb", "REL_OP": ">", "RIGHT_ID": "wh_word",
                 "RIGHT_ATTRS": {"DEP": "advmod", "TAG": {"IN": ["WRB", "WP"]}}},
                {"LEFT_ID": "be_verb", "REL_OP": ">", "RIGHT_ID": "quest_mark",
                 "RIGHT_ATTRS": {"ORTH": "?"}},
            ]])

            # 12. Can ability  e.g. "I can swim."
            matcher.add("can_ability", [[
                {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"DEP": "ROOT", "POS": "VERB"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "modal_can",
                 "RIGHT_ATTRS": {"LOWER": "can", "DEP": "aux"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
            ]])

            # 13. Want statement  e.g. "I want a comic book."
            matcher.add("want_statement", [[
                {"RIGHT_ID": "want_verb", "RIGHT_ATTRS": {"LEMMA": "want", "DEP": "ROOT"}},
                {"LEFT_ID": "want_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "want_verb", "REL_OP": ">", "RIGHT_ID": "obj",
                 "RIGHT_ATTRS": {"DEP": "dobj"}},
            ]])

            # 14. Let's suggestion  e.g. "Let's go shopping."
            matcher.add("lets_suggestion", [[
                {"RIGHT_ID": "let_verb", "RIGHT_ATTRS": {"LOWER": "let", "DEP": "ROOT"}},
                {"LEFT_ID": "let_verb", "REL_OP": ">", "RIGHT_ID": "suggestion_verb",
                 "RIGHT_ATTRS": {"DEP": "ccomp"}},
            ]])

            # 15. Going-to future  e.g. "I am going to visit my grandparents."
            matcher.add("going_to_future", [[
                {"RIGHT_ID": "going_verb", "RIGHT_ATTRS": {"LEMMA": "go", "DEP": "ROOT"}},
                {"LEFT_ID": "going_verb", "REL_OP": ">", "RIGHT_ID": "be_aux",
                 "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "aux"}},
                {"LEFT_ID": "going_verb", "REL_OP": ">", "RIGHT_ID": "future_verb",
                 "RIGHT_ATTRS": {"DEP": "xcomp"}},
            ]])

            # 16. Be + prepositional phrase  e.g. "It is on the table."
            matcher.add("be_prepositional", [[
                {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
                {"LEFT_ID": "be_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "be_verb", "REL_OP": ">", "RIGHT_ID": "prep",
                 "RIGHT_ATTRS": {"DEP": "prep"}},
            ]])

            # 17. Modal advice/future  e.g. "You should eat vegetables."
            matcher.add("should_will_modal", [[
                {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"DEP": "ROOT", "POS": "VERB"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "modal",
                 "RIGHT_ATTRS": {"TAG": "MD", "DEP": "aux"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
            ]])

            # 18. Can't / cannot  e.g. "I can't swim."
            matcher.add("cant_negative", [[
                {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"DEP": "ROOT", "POS": "VERB"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "modal_can",
                 "RIGHT_ATTRS": {"LEMMA": "can", "DEP": "aux"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "negation",
                 "RIGHT_ATTRS": {"DEP": "neg"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
            ]])

            # 19. Positive imperative  e.g. "Open the door."  "Try this."
            matcher.add("imperative", [[
                {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"TAG": "VB", "DEP": "ROOT"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "obj",
                 "RIGHT_ATTRS": {"DEP": "dobj"}},
            ]])

            # 20. Like + gerund  e.g. "I like playing basketball."
            matcher.add("like_gerund", [[
                {"RIGHT_ID": "like_verb", "RIGHT_ATTRS": {"LEMMA": "like", "DEP": "ROOT"}},
                {"LEFT_ID": "like_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "like_verb", "REL_OP": ">", "RIGHT_ID": "gerund",
                 "RIGHT_ATTRS": {"DEP": "xcomp", "TAG": "VBG"}},
            ]])

            # 21. Want + to-infinitive  e.g. "I want to be a scientist."
            matcher.add("want_to_inf", [[
                {"RIGHT_ID": "want_verb", "RIGHT_ATTRS": {"LEMMA": "want", "DEP": "ROOT"}},
                {"LEFT_ID": "want_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "want_verb", "REL_OP": ">", "RIGHT_ID": "inf_clause",
                 "RIGHT_ATTRS": {"DEP": "xcomp"}},
            ]])

            # 22. How about + gerund  e.g. "How about playing tennis?"
            matcher.add("how_about", [[
                {"RIGHT_ID": "about_root", "RIGHT_ATTRS": {"LOWER": "about", "DEP": "ROOT"}},
                {"LEFT_ID": "about_root", "REL_OP": ">", "RIGHT_ID": "how_word",
                 "RIGHT_ATTRS": {"LOWER": "how", "DEP": "advmod"}},
            ]])

            # 23. Simple SVO  e.g. "I cleaned the street."
            matcher.add("simple_svo", [[
                {"RIGHT_ID": "root_verb",
                 "RIGHT_ATTRS": {"DEP": "ROOT", "POS": "VERB",
                                 "TAG": {"IN": ["VBD", "VBP", "VBZ"]}}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "obj",
                 "RIGHT_ATTRS": {"DEP": "dobj"}},
            ]])

            # 24. Looks/sounds/feels + adjective  e.g. "That looks fun."
            matcher.add("looks_sounds_adj", [[
                {"RIGHT_ID": "sense_verb",
                 "RIGHT_ATTRS": {"LEMMA": {"IN": ["look", "sound", "seem", "feel",
                                                   "smell", "taste"]},
                                 "DEP": "ROOT"}},
                {"LEFT_ID": "sense_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "sense_verb", "REL_OP": ">", "RIGHT_ID": "adj",
                 "RIGHT_ATTRS": {"DEP": "acomp"}},
            ]])

            # 25. Go to place  e.g. "I go to school."
            matcher.add("go_to_place", [[
                {"RIGHT_ID": "go_verb", "RIGHT_ATTRS": {"LEMMA": "go", "DEP": "ROOT"}},
                {"LEFT_ID": "go_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "go_verb", "REL_OP": ">", "RIGHT_ID": "to_prep",
                 "RIGHT_ATTRS": {"LOWER": "to", "DEP": "prep"}},
            ]])

            # 26. Whose question  e.g. "Whose pen is this?"
            matcher.add("whose_question", [[
                {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
                {"LEFT_ID": "be_verb", "REL_OP": ">", "RIGHT_ID": "thing",
                 "RIGHT_ATTRS": {"DEP": "attr", "POS": "NOUN"}},
                {"LEFT_ID": "thing", "REL_OP": ">", "RIGHT_ID": "whose_poss",
                 "RIGHT_ATTRS": {"LOWER": "whose", "DEP": "poss"}},
                {"LEFT_ID": "be_verb", "REL_OP": ">", "RIGHT_ID": "quest_mark",
                 "RIGHT_ATTRS": {"ORTH": "?"}},
            ]])

            # 27. Don't / negative imperative  e.g. "Don't run."
            matcher.add("dont_imperative", [[
                {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"TAG": "VB", "DEP": "ROOT"}},
                {"LEFT_ID": "root_verb", "REL_OP": ">", "RIGHT_ID": "negation",
                 "RIGHT_ATTRS": {"DEP": "neg"}},
            ]])

            # 28. Short yes/no answer with do  e.g. "Yes, I did."
            matcher.add("short_answer_do", [[
                {"RIGHT_ID": "do_verb", "RIGHT_ATTRS": {"LEMMA": "do", "DEP": "ROOT"}},
                {"LEFT_ID": "do_verb", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
                {"LEFT_ID": "do_verb", "REL_OP": ">", "RIGHT_ID": "yes_no",
                 "RIGHT_ATTRS": {"LOWER": {"IN": ["yes", "no"]}, "DEP": "intj"}},
            ]])

            # 29. No, can't response  e.g. "No, you can't."
            matcher.add("no_cant_response", [[
                {"RIGHT_ID": "can_root", "RIGHT_ATTRS": {"LEMMA": "can", "DEP": "ROOT"}},
                {"LEFT_ID": "can_root", "REL_OP": ">", "RIGHT_ID": "negation",
                 "RIGHT_ATTRS": {"DEP": "neg"}},
                {"LEFT_ID": "can_root", "REL_OP": ">", "RIGHT_ID": "subj",
                 "RIGHT_ATTRS": {"DEP": "nsubj"}},
            ]])

            self._grammar_matcher = matcher
            logger.info("Grammar DependencyMatcher loaded with %d pattern(s)", len(matcher))
        except Exception as exc:
            logger.warning("Grammar matcher failed to initialise: %s", exc)
        return self._grammar_matcher

    def _extract_grammar_candidates(self, doc: Any) -> list[dict]:
        """Run the DependencyMatcher over a single spaCy Doc.

        Returns one candidate per matched sentence. When multiple patterns fire
        on the same sentence the text is emitted exactly once; all triggered
        pattern names are collected into metadata['patterns'].

        Note: _is_imperative is intentionally NOT applied here. The grammar tier
        is additive and structural — imperative sentences (pattern 19, 27) are
        valid ESL teaching examples that should be identified, not filtered.
        """
        matcher = self._load_grammar_matcher()
        nlp = self._load_nlp()
        if matcher is None or nlp is None or doc is None:
            return []

        try:
            matches = matcher(doc)
        except Exception as exc:
            logger.warning("DependencyMatcher failed on doc: %s", exc)
            return []

        # Group all fired pattern names by the sentence they belong to
        sent_patterns: dict[int, list[str]] = {}
        for match_id, token_ids in matches:
            if not token_ids:
                continue
            try:
                sent_start = doc[token_ids[0]].sent.start
            except Exception:
                continue
            pattern_name = nlp.vocab.strings[match_id]
            sent_patterns.setdefault(sent_start, []).append(pattern_name)

        candidates: list[dict] = []
        seen_norms: set[str] = set()

        for sent in doc.sents:
            if sent.start not in sent_patterns:
                continue
            sent_text = sent.text.strip()
            if not sent_text:
                continue
            norm = _normalize_text(sent_text)
            if norm in seen_norms:
                continue
            seen_norms.add(norm)
            # Deduplicate pattern names while preserving first-fired order
            patterns_seen = list(dict.fromkeys(sent_patterns[sent.start]))
            candidates.append({
                "candidateType": CANDIDATE_TYPE_GRAMMAR,
                "text": sent_text,
                "normalizedText": norm,
                "sourceBlockId": None,       # caller fills block provenance
                "sourcePageNumber": None,
                "sourceSlideNumber": None,
                "confidence": _GRAMMAR_CONFIDENCE,
                "metadata": {
                    "engine": "dependency_matcher",
                    "patterns": patterns_seen,
                },
            })

        return candidates

    def _detect_grammar(self, blocks: list[dict]) -> list[dict]:
        """Detect grammar patterns across all blocks; deduplicates across blocks."""
        nlp = self._load_nlp()
        if nlp is None:
            return []

        candidates: list[dict] = []
        seen_norms: set[str] = set()   # cross-block deduplication

        for block in blocks:
            block_text = block.get("text") or ""
            if not block_text.strip():
                continue

            block_id = block.get("blockId") or block.get("id")
            source = block.get("source") if isinstance(block.get("source"), dict) else {}
            page_number = source.get("pageNumber")
            slide_number = source.get("slideNumber")

            try:
                doc = nlp(block_text)
            except Exception as exc:
                logger.warning("spaCy parse failed on block: %s", exc)
                continue

            for cand in self._extract_grammar_candidates(doc):
                if cand["normalizedText"] in seen_norms:
                    continue
                seen_norms.add(cand["normalizedText"])
                cand["sourceBlockId"] = str(block_id) if block_id is not None else None
                cand["sourcePageNumber"] = page_number
                cand["sourceSlideNumber"] = slide_number
                candidates.append(cand)

        return candidates

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

            # Prefer spaCy Span objects so _is_imperative can inspect parsed tokens.
            # Fall back to plain strings only when spaCy is unavailable.
            spacy_spans: list[Any] | None = None
            fallback_strings: list[str] = []
            if nlp is not None:
                try:
                    doc = nlp(block_text)
                    spacy_spans = [s for s in doc.sents if s.text.strip()]
                except Exception:
                    fallback_strings = [s.strip() for s in block_text.split(". ") if s.strip()]
            else:
                fallback_strings = [s.strip() for s in block_text.split(". ") if s.strip()]

            items: list[Any] = spacy_spans if spacy_spans is not None else fallback_strings

            for item in items:
                using_span = spacy_spans is not None
                sentence = item.text.strip() if using_span else item
                if not sentence:
                    continue

                # Drop imperative sentences (teacher instructions like "Read the passage.")
                if using_span and self._is_imperative(item):
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

                # Lexical anchor: single-token headwords bypass BM25S/KeyBERT top-N
                # requirements and are promoted directly to 0.95 confidence.
                if token_count == 1 and keyphrase in self._anchor_words:
                    tier = "lexical_anchor"
                    confidence = _LEXICAL_ANCHOR_CONFIDENCE
                else:
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

        # 5. Grammar pattern detection via DependencyMatcher
        try:
            candidates.extend(self._detect_grammar(blocks))
        except Exception as exc:
            logger.warning("Grammar detection failed: %s", exc)

        # 6. Deduplicate by normalizedText, keeping highest confidence
        seen: dict[str, dict] = {}
        for cand in candidates:
            key = cand["normalizedText"]
            if key not in seen or cand["confidence"] > seen[key]["confidence"]:
                seen[key] = cand

        # 7. Sort by confidence descending
        return sorted(seen.values(), key=lambda c: c["confidence"], reverse=True)
