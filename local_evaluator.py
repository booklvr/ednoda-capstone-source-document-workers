#!/usr/bin/env python3
"""
Local NLU evaluation script.

Scans data/ for supported files (PDF, DOCX, TXT, CSV, PPTX), extracts plain text,
runs it through SlidingWindowChunker + NLULabeller, and writes per-file JSON output
to data/results/{filename}_analysis.json grouped by candidate type.

Usage:
    python local_evaluator.py
    python local_evaluator.py --data-dir path/to/other/dir
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WORKERS_DIR = ROOT / "workers"
CANDIDATE_DIR = WORKERS_DIR / "candidate-extractor-stub"

for _path in (WORKERS_DIR, CANDIDATE_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from chunker import SlidingWindowChunker  # noqa: E402
from cleaner import TextCleaner  # noqa: E402
from labeller import NLULabeller  # noqa: E402

try:
    from langdetect import DetectorFactory, detect as _langdetect_detect
    DetectorFactory.seed = 0  # deterministic results across runs
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False
    print("WARNING: langdetect not installed — English gate disabled", file=sys.stderr)

SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".txt", ".csv", ".pptx"})
_LEXICAL_TARGETS_FILE = ROOT / "data" / "lexical_targets.txt"


def _load_anchor_words(path: Path) -> frozenset[str]:
    if not path.exists():
        print(f"[WARN] lexical targets file not found: {path} — anchor tier disabled", file=sys.stderr)
        return frozenset()
    words: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if word and not word.startswith("#"):
            words.add(word)
    print(f"Loaded {len(words)} lexical anchor word(s) from {path.relative_to(ROOT)}")
    return frozenset(words)
_BM25S_WORD_THRESHOLD = 200
_BM25S_SMALL_CHUNK_SIZE = 75
_DEFAULT_CHUNK_SIZE = 200


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_pdf(path: Path) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(str(path))
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages)


def _extract_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_pptx(path: Path) -> str:
    from pptx import Presentation
    prs = Presentation(str(path))
    slides: list[str] = []
    for slide in prs.slides:
        texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in para.runs).strip()
                    if line:
                        texts.append(line)
        if texts:
            slides.append(" ".join(texts))
    return "\n".join(slides)


def _extract_csv(path: Path) -> str:
    import csv
    rows: list[str] = []
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.reader(fh):
            line = " ".join(cell.strip() for cell in row if cell.strip())
            if line:
                rows.append(line)
    return "\n".join(rows)


def _extract_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


_EXTRACTORS = {
    ".pdf":  _extract_pdf,
    ".docx": _extract_docx,
    ".pptx": _extract_pptx,
    ".csv":  _extract_csv,
    ".txt":  _extract_txt,
}


def extract_text(path: Path) -> str | None:
    extractor = _EXTRACTORS.get(path.suffix.lower())
    if extractor is None:
        return None
    try:
        return extractor(path)
    except Exception as exc:
        print(f"  [WARN] text extraction failed for {path.name}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Mock blocks
# ---------------------------------------------------------------------------

def _split_sentences(plain_text: str) -> list[str]:
    try:
        import spacy
        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            nlp = spacy.blank("en")
            nlp.add_pipe("sentencizer")
        return [s.text.strip() for s in nlp(plain_text).sents if s.text.strip()]
    except Exception:
        pass
    # Fallback: split on ". "
    parts = plain_text.split(". ")
    sentences: list[str] = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        sentences.append(part + "." if i < len(parts) - 1 else part)
    return sentences


def build_mock_blocks(sentences: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "text": sentence,
            "source": {"pageNumber": idx + 1, "slideNumber": None},
        }
        for idx, sentence in enumerate(sentences)
    ]


# ---------------------------------------------------------------------------
# English-only language gate
# ---------------------------------------------------------------------------

# Architectural Decision: As an English learning platform, we strictly gate
# non-English text to prevent spaCy misparsing and to filter out native-language
# teacher instructions. Korean, Japanese, Chinese, and other non-English sentences
# are silently discarded before reaching BM25S, KeyBERT, or the spaCy question
# detector. Sentences that are too short for reliable detection (<4 tokens) are
# kept, as are sentences where detection fails — both cases default to inclusion
# to avoid discarding ambiguous English fragments.

# Unicode ranges for scripts that should never appear in English sentences.
_NON_LATIN_RANGES = (
    ('가', '힯'),  # Hangul syllables
    ('ᄀ', 'ᇿ'),  # Hangul jamo
    ('㄰', '㆏'),  # Hangul compatibility jamo
    ('ꥠ', '꥿'),  # Hangul jamo extended-A
    ('ힰ', '퟿'),  # Hangul jamo extended-B
    ('一', '鿿'),  # CJK unified ideographs
    ('　', '〿'),  # CJK symbols and punctuation
    ('぀', 'ゟ'),  # Hiragana
    ('゠', 'ヿ'),  # Katakana
)


def _contains_non_latin_script(text: str) -> bool:
    return any(lo <= ch <= hi for ch in text for lo, hi in _NON_LATIN_RANGES)


def _is_garbled(text: str) -> bool:
    """True when most 'words' are single characters — indicates bad PDF glyph extraction."""
    words = text.split()
    if len(words) < 4:
        return False
    single_char = sum(1 for w in words if len(w) == 1)
    return single_char / len(words) > 0.5


def is_target_language(text: str, target_lang_code: str = "en") -> bool:
    # CJK / Hangul hard-reject is only meaningful when the target is English.
    # For other target languages the non-Latin check would incorrectly discard
    # valid content (e.g. a Japanese course would need Japanese characters).
    if target_lang_code == "en" and _contains_non_latin_script(text):
        return False
    if _is_garbled(text):
        return False
    if not _LANGDETECT_AVAILABLE:
        return True
    if len(text.split()) < 4:
        return True  # too short for reliable detection → keep
    try:
        return _langdetect_detect(text) == target_lang_code
    except Exception:
        return True  # detection failure → include


def filter_target_language_sentences(
    sentences: list[str],
    target_lang_code: str = "en",
    label: str = "",
) -> list[str]:
    filtered = [s for s in sentences if is_target_language(s, target_lang_code)]
    dropped = len(sentences) - len(filtered)
    if dropped:
        tag = f" from {label}" if label else ""
        print(f"  [lang gate] dropped {dropped}/{len(sentences)} non-{target_lang_code} sentences{tag}")
    return filtered


# ---------------------------------------------------------------------------
# Type grouping
# ---------------------------------------------------------------------------

def group_by_type(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "lexical_anchor_nodes_0.95": [],
        "vocabulary_nodes_0.91": [],
        "grammar_nodes_0.80": [],
        "expression_nodes_0.72": [],
        "question_nodes_0.60": [],
    }
    for candidate in candidates:
        ctype = candidate.get("candidateType", "")
        engine = (candidate.get("metadata") or {}).get("engine", "")
        if ctype == "vocab" and engine == "lexical_anchor":
            groups["lexical_anchor_nodes_0.95"].append(candidate)
        elif ctype == "vocab":
            groups["vocabulary_nodes_0.91"].append(candidate)
        elif ctype == "grammar":
            groups["grammar_nodes_0.80"].append(candidate)
        elif ctype == "expression":
            groups["expression_nodes_0.72"].append(candidate)
        elif ctype == "question":
            groups["question_nodes_0.60"].append(candidate)
        # unknown → omitted
    return groups


# ---------------------------------------------------------------------------
# Human-readable text output
# ---------------------------------------------------------------------------

def write_readable_txt(
    path: Path,
    groups: dict[str, list[dict[str, Any]]],
    total: int,
    extracted_dir: Path,
    root: Path,
) -> None:
    lines: list[str] = [
        f"Source Document: {path.name}",
        f"Total Candidates: {total}",
        "",
        "=== LEXICAL ANCHOR TIER (0.95) - ESL HEADWORDS ===",
    ]
    anchor = groups["lexical_anchor_nodes_0.95"]
    lines += [f"- {c['text']}" for c in anchor] if anchor else ["(none)"]

    lines += ["", "=== AGREEMENT TIER (0.91) - VOCABULARY ==="]
    vocab = groups["vocabulary_nodes_0.91"]
    lines += [f"- {c['text']}" for c in vocab] if vocab else ["(none)"]

    lines += ["", "=== GRAMMAR TIER (0.80) - GRAMMAR PATTERNS ==="]
    grammar = groups["grammar_nodes_0.80"]
    lines += [f"- {c['text']}" for c in grammar] if grammar else ["(none)"]

    lines += ["", "=== FALLBACK TIER (0.72) - EXPRESSIONS ==="]
    expr = groups["expression_nodes_0.72"]
    lines += [f"- {c['text']}" for c in expr] if expr else ["(none)"]

    lines += ["", "=== QUESTION TIER (0.60) - SPACY PATTERNS ==="]
    qs = groups["question_nodes_0.60"]
    lines += [f"- {c['text']}" for c in qs] if qs else ["(none)"]

    extracted_dir.mkdir(parents=True, exist_ok=True)
    txt_path = extracted_dir / f"{path.stem}_readable.txt"
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote → {txt_path.relative_to(root)}")


# ---------------------------------------------------------------------------
# Per-file evaluation
# ---------------------------------------------------------------------------

def evaluate_file(
    path: Path,
    results_dir: Path,
    extracted_dir: Path,
    raw_dumps_dir: Path,
    root: Path,
    anchor_words: frozenset[str] = frozenset(),
) -> bool:
    print(f"\nProcessing: {path.relative_to(root)}")

    plain_text = extract_text(path)
    if not plain_text or not plain_text.strip():
        print("  [SKIP] no text extracted")
        return False

    # ---- raw dump: save unmodified extractor output before any processing ----
    raw_dumps_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dumps_dir / f"{path.stem}_raw.txt"
    raw_path.write_text(plain_text, encoding="utf-8", errors="replace")

    # Remove boilerplate/noise lines before any NLU processing
    plain_text = TextCleaner().clean(plain_text)
    if not plain_text.strip():
        print("  [SKIP] no content remaining after cleaning")
        return False

    # Split into sentences, then apply the language gate before any NLU processing
    raw_sentences = _split_sentences(plain_text)

    # =====================================================================
    # LANGUAGE CONFIGURATION GATE
    # =====================================================================
    # TODO (AWS DEPLOYMENT): This target language code ('en') is currently
    # set as the default for local testing. For production, this MUST be
    # dynamically injected from the Ednoda database based on the Course/Lesson
    # metadata. To switch languages locally, change `target_lang_code` below.
    # =====================================================================
    target_lang_code = "en"

    target_sentences = filter_target_language_sentences(
        raw_sentences, target_lang_code=target_lang_code, label=path.name
    )
    if not target_sentences:
        print(f"  [SKIP] no {target_lang_code} content detected after language gate")
        return False

    plain_text_en = " ".join(target_sentences)
    mock_blocks = build_mock_blocks(target_sentences)

    word_count = len(plain_text_en.split())
    print(f"  {target_lang_code} words: {word_count} (raw: {len(plain_text.split())})")

    if word_count < _BM25S_WORD_THRESHOLD:
        chunk_size = _BM25S_SMALL_CHUNK_SIZE
        print(f"  [BM25S guardrail] word count < {_BM25S_WORD_THRESHOLD} → chunk_size={chunk_size}")
    else:
        chunk_size = _DEFAULT_CHUNK_SIZE

    chunks = SlidingWindowChunker(chunk_size=chunk_size).chunk(plain_text_en, mock_blocks)
    candidates = NLULabeller(anchor_words=anchor_words).label(chunks, mock_blocks)

    groups = group_by_type(candidates)
    total = sum(len(v) for v in groups.values())
    print(
        f"  candidates: {total} total  "
        f"({len(groups['lexical_anchor_nodes_0.95'])} anchor, "
        f"{len(groups['vocabulary_nodes_0.91'])} vocab, "
        f"{len(groups['grammar_nodes_0.80'])} grammar, "
        f"{len(groups['expression_nodes_0.72'])} expression, "
        f"{len(groups['question_nodes_0.60'])} question)"
    )

    output = {
        "document_name": path.name,
        "format": path.suffix.lower().lstrip("."),
        "total_nodes_found": total,
        "extracted_content": groups,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / f"{path.stem}_analysis.json"
    json_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  wrote → {json_path.relative_to(root)}")

    write_readable_txt(path, groups, total, extracted_dir, root)
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "data",
        help="Directory to scan for source files (default: data/)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir: Path = args.data_dir
    results_dir = data_dir / "results"
    extracted_dir = data_dir / "extracted"
    raw_dumps_dir = data_dir / "raw_dumps"

    if not data_dir.exists():
        print(f"Error: data directory not found: {data_dir}", file=sys.stderr)
        return 1

    anchor_words = _load_anchor_words(_LEXICAL_TARGETS_FILE)

    files = sorted(
        f for f in data_dir.rglob("*")
        if f.is_file()
        and f.suffix.lower() in SUPPORTED_SUFFIXES
        and f != _LEXICAL_TARGETS_FILE
        and results_dir not in f.parents
        and extracted_dir not in f.parents
        and raw_dumps_dir not in f.parents
    )

    if not files:
        print(f"No supported files found in {data_dir}", file=sys.stderr)
        return 1

    print(f"Found {len(files)} file(s) to evaluate:")
    for f in files:
        print(f"  {f.relative_to(ROOT)}")

    processed = 0
    for f in files:
        if evaluate_file(
            f,
            results_dir=results_dir,
            extracted_dir=extracted_dir,
            raw_dumps_dir=raw_dumps_dir,
            root=ROOT,
            anchor_words=anchor_words,
        ):
            processed += 1

    print(
        f"\nDone. {processed}/{len(files)} files processed. "
        f"JSON → {results_dir.relative_to(ROOT)}/  "
        f"Text → {extracted_dir.relative_to(ROOT)}/  "
        f"Raw → {raw_dumps_dir.relative_to(ROOT)}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
