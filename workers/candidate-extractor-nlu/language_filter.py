"""Target-language gate — Stage A of candidate quality/language hardening.

See 062526-candidate-quality-language-hardening.md.

Source textbooks are bilingual (e.g. Korean L1 explanation + English L2 target).
We only want candidates in the *target language*. BM25 scores terms by rarity,
so rare other-language tokens get promoted to the top — exactly the wrong
behaviour. The cheapest, most reliable fix is to drop other-language text at the
source, before BM25/KeyBERT ever see it.

============================  ENGLISH-DEFAULT NOTICE  =========================
The target language is CONFIG, not a hardcoded constant. It defaults to "en"
today because we are testing on English data. It is NOT silently baked in:
  - the default lives in DEFAULT_TARGET_LANGUAGE below, and
  - the detector is pluggable (see ScriptLanguageDetector) so a future detector
    can handle Latin-vs-Latin language pairs (e.g. French/English).
If you are adding a non-English target language, search this file for
"ENGLISH-DEFAULT" and "LATIN-SCRIPT ASSUMPTION" comments — those are the places
that assume the target is an English/Latin-script language.
==============================================================================
"""

from __future__ import annotations

# ENGLISH-DEFAULT: target language defaults to English for the current MVP.
DEFAULT_TARGET_LANGUAGE = "en"

# LATIN-SCRIPT ASSUMPTION: the default script detector can only tell apart the
# script families it knows about. Map language codes to a script family here.
# Languages not listed fall back to "latin" (the English-default assumption).
_LANGUAGE_SCRIPT_FAMILY = {
    "en": "latin",
    "fr": "latin",
    "es": "latin",
    "de": "latin",
    "ko": "hangul",
}


def _hangul_count(text: str) -> int:
    # Hangul syllables + Jamo blocks. LATIN-SCRIPT ASSUMPTION: we only special-
    # case Hangul here because current source data is Korean/English. A general
    # detector would replace this script-counting heuristic.
    return sum(1 for ch in text if "가" <= ch <= "힣" or "ᄀ" <= ch <= "ᇿ")


def _latin_letter_count(text: str) -> int:
    return sum(1 for ch in text if ("a" <= ch.lower() <= "z"))


class ScriptLanguageDetector:
    """Default detector: classify a line by dominant script.

    Pluggable by design — anything with an ``is_target(text, target_language)``
    method can be passed to ``filter_to_target_language`` as ``detector``.
    """

    def is_target(self, text: str, target_language: str) -> bool:
        # LATIN-SCRIPT ASSUMPTION: classify the line by dominant script and keep
        # it only when that script matches the target language's script family.
        # Unknown target codes default to "latin" (the English-default path).
        family = _LANGUAGE_SCRIPT_FAMILY.get(target_language, "latin")
        latin = _latin_letter_count(text)
        hangul = _hangul_count(text)
        if family == "hangul":
            # Keep Hangul-dominant lines; lines with no Hangul are not target.
            return hangul > 0 and hangul >= latin
        # family == "latin": keep Latin-dominant lines; pure-other-script drops.
        if hangul == 0:
            return True
        return latin >= hangul


def _token_is_foreign(token: str, target_language: str) -> bool:
    """True if a whitespace token belongs to a non-target script.

    LATIN-SCRIPT ASSUMPTION: for a Latin-script target (e.g. en) a token is
    foreign if it contains any Hangul; for a Hangul target, foreign if it
    contains any Latin letter.
    """
    family = _LANGUAGE_SCRIPT_FAMILY.get(target_language, "latin")
    if family == "hangul":
        return _latin_letter_count(token) > 0
    return _hangul_count(token) > 0


def is_target_phrase(phrase: str, target_language: str = DEFAULT_TARGET_LANGUAGE) -> bool:
    """Strict check for a candidate phrase: reject if ANY token is foreign-script.

    Used at candidate emission so a mixed phrase like ``robot 로봇`` is rejected
    for an English target (the line-level gate alone is too permissive on real
    bilingual text).
    """
    return all(not _token_is_foreign(token, target_language) for token in phrase.split())


def filter_to_target_language(
    text: str,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    detector: ScriptLanguageDetector | None = None,  # reserved for a future pluggable detector
) -> str:
    """Return ``text`` with non-target-language content removed at TOKEN level.

    Strips foreign-script tokens even within mixed/bilingual lines (real Korean
    ESL pages interleave Korean and English on the same line), then drops lines
    left empty. Stricter and more robust than line-level filtering: a bilingual
    line keeps only its target-language words.
    """
    kept: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            kept.append(line)
            continue
        tokens = [t for t in line.split() if not _token_is_foreign(t, target_language)]
        rebuilt = " ".join(tokens).strip()
        if rebuilt:
            kept.append(rebuilt)
    return "\n".join(kept)
