"""Preprocessing composition — Stage A of candidate quality/language hardening.

See 062526-candidate-quality-language-hardening.md.

Turns raw extracted plain text into target-language-only, de-noised text ready
for chunking. Order matters:

  1. target-language gate FIRST, on raw lines — so a bilingual document drops its
     other-language lines before the cleaner's mid-sentence stitching can merge a
     dropped-language line into a kept one.
  2. cleaner SECOND — removes running headers/footers, page furniture, speaker
     tags, standalone numbers, boilerplate, and stitches line-wrapped sentences.
"""

from __future__ import annotations

import os

from cleaner import TextCleaner
from language_filter import DEFAULT_TARGET_LANGUAGE, filter_to_target_language

# ENGLISH-DEFAULT: the target language is configuration, not a hardcoded
# constant. Today it is read from this env var, defaulting to English. The
# input contract does not yet carry a target-language field; WHEN IT DOES, read
# it from the handoff here (and keep this env var as the fallback).
_TARGET_LANGUAGE_ENV_VAR = "CANDIDATE_TARGET_LANGUAGE"


def resolve_target_language() -> str:
    """Resolve the configured target language, defaulting to English."""
    value = os.environ.get(_TARGET_LANGUAGE_ENV_VAR, "").strip()
    return value or DEFAULT_TARGET_LANGUAGE


def preprocess_text(
    text: str,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
) -> str:
    """Gate to the target language, then clean scraped-data noise."""
    target_only = filter_to_target_language(text, target_language)
    return TextCleaner().clean(target_only)
