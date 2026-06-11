"""
Syntactic accuracy tests for all 29 DependencyMatcher grammar patterns.

Each pattern gets one canonical sentence drawn from the examples in patterns.py.
The parametrized test verifies the pattern fires; five additional named
assertions satisfy the explicit task-spec requirements.
Three graceful-degradation tests confirm the pipeline returns [] rather than
raising when given empty, garbled, or a manually disabled matcher.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "workers", ROOT / "workers" / "candidate-extractor-stub"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest
import spacy

from labeller import NLULabeller


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def nlp():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        pytest.skip("en_core_web_sm not installed — skipping grammar pattern tests")


@pytest.fixture(scope="session")
def lab(nlp):
    instance = NLULabeller()
    instance._load_grammar_matcher()   # warm up
    instance._load_nlp()
    return instance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fired_patterns(lab_obj: NLULabeller, nlp_model, sentence: str) -> set[str]:
    """Return the set of pattern names that fire on the sentence."""
    doc = nlp_model(sentence)
    candidates = lab_obj._extract_grammar_candidates(doc)
    return {p for c in candidates for p in c["metadata"]["patterns"]}


# ---------------------------------------------------------------------------
# 29-pattern parametrized suite
# One canonical sentence per pattern, taken directly from patterns.py comments.
# ---------------------------------------------------------------------------

PATTERN_CASES = [
    # (pattern_name, canonical_sentence)
    ("present_simple_question", "Do you like pizza?"),
    ("there_is_are",            "There is a dog."),
    ("comparative",             "A lion is bigger than a dog."),
    ("present_continuous",      "She is listening to music."),
    ("be_attr_statement",       "My name is Tom."),
    ("be_adjective",            "The bus is big."),
    ("can_question",            "Can you help me?"),
    ("like_statement",          "I like milk."),
    ("be_from_place",           "I am from Canada."),
    ("have_statement",          "I have scissors."),
    ("wh_question_be",          "How are you?"),
    ("can_ability",             "I can swim."),
    ("want_statement",          "I want a comic book."),
    ("lets_suggestion",         "Let's go to the park."),
    ("going_to_future",         "I am going to visit my grandparents."),
    ("be_prepositional",        "It is on the table."),
    ("should_will_modal",       "You should eat vegetables."),
    ("cant_negative",           "I can't swim."),
    ("imperative",              "Open the door."),
    ("like_gerund",             "I like playing basketball."),
    ("want_to_inf",             "I want to be a scientist."),
    ("how_about",               "How about playing tennis?"),
    ("simple_svo",              "I cleaned the street."),
    ("looks_sounds_adj",        "That looks fun."),
    ("go_to_place",             "I go to school."),
    ("whose_question",          "Whose pen is this?"),
    ("dont_imperative",         "Don't worry."),
    ("short_answer_do",         "Yes, I did."),
    ("no_cant_response",        "No, you can't."),
]


@pytest.mark.parametrize(
    "pattern_name, sentence",
    PATTERN_CASES,
    ids=[name for name, _ in PATTERN_CASES],
)
def test_pattern_fires(pattern_name: str, sentence: str, lab, nlp):
    fired = _fired_patterns(lab, nlp, sentence)
    assert pattern_name in fired, (
        f"Pattern '{pattern_name}' did not fire on: {sentence!r}\n"
        f"Patterns that DID fire: {sorted(fired) or '(none)'}"
    )


# ---------------------------------------------------------------------------
# Named assertions — exact sentences from the task spec
# ---------------------------------------------------------------------------

def test_spec_present_simple_question(lab, nlp):
    assert "present_simple_question" in _fired_patterns(lab, nlp, "Do you like pizza?")

def test_spec_there_is_are(lab, nlp):
    assert "there_is_are" in _fired_patterns(lab, nlp, "There is a dog.")

def test_spec_present_continuous(lab, nlp):
    assert "present_continuous" in _fired_patterns(lab, nlp, "She is listening to music.")

def test_spec_how_about(lab, nlp):
    assert "how_about" in _fired_patterns(lab, nlp, "How about playing tennis?")

def test_spec_dont_imperative(lab, nlp):
    assert "dont_imperative" in _fired_patterns(lab, nlp, "Don't worry.")


# ---------------------------------------------------------------------------
# Multi-pattern deduplication
# A sentence that fires multiple patterns must appear exactly once.
# ---------------------------------------------------------------------------

def test_multi_pattern_sentence_deduplicated(lab, nlp):
    # "I can't swim." fires both cant_negative and possibly can_ability — one candidate only
    doc = nlp("I can't swim.")
    candidates = lab._extract_grammar_candidates(doc)
    texts = [c["text"] for c in candidates]
    assert len(texts) == len(set(texts)), "Duplicate sentence in grammar candidates"


def test_multi_pattern_all_names_collected(lab, nlp):
    # "I like playing basketball." fires like_gerund; verify metadata list is non-empty
    doc = nlp("I like playing basketball.")
    candidates = lab._extract_grammar_candidates(doc)
    assert candidates, "Expected at least one grammar candidate"
    for c in candidates:
        assert isinstance(c["metadata"]["patterns"], list)
        assert len(c["metadata"]["patterns"]) >= 1


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

def test_empty_string_returns_empty_list(lab, nlp):
    doc = nlp("")
    assert lab._extract_grammar_candidates(doc) == []


def test_garbled_fragment_returns_list(lab, nlp):
    doc = nlp("!!!###@@@")
    result = lab._extract_grammar_candidates(doc)
    assert isinstance(result, list)   # no exception; may be empty


def test_disabled_matcher_returns_empty(nlp):
    instance = NLULabeller()
    instance._grammar_matcher = None
    instance._grammar_matcher_loaded = True
    doc = nlp("She is happy.")
    assert instance._extract_grammar_candidates(doc) == []
