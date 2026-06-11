## NLU Extraction Pipeline: Architecture & Development Log
**Dates:** 2026-05-29 to 2026-06-09  
**Core Problem:** Signal Extraction and Noise Filtering

Source educational documents (lesson plans, grammar worksheets, slide decks, and teacher manuals) are notoriously messy. They interleave teacher-facing administrative instructions, native-language translation notes, page numbers, and formatting artifacts with the actual English learning content. 

This pipeline acts as a **sieve**. Our job is to strip away the administrative noise, protect the pedagogical signal, and produce a clean, tiered output of Education Nodes (Vocabulary, Expressions, Grammar, Questions) that the Ednoda platform can confidently ingest.

## Part 1: System Architecture & Feature Reference
*For future developers: How the pipeline works, why it exists, and where to modify it.*

### Layer 1: Smart Text Cleaning & Formatting Restoration
* **Where:** `cleaner.py` -> `TextCleaner.clean()`
* **What it does:** Strips boilerplate lines (e.g., "Aims", "Learning Objectives", "Grade X"), stitches PDF mid-sentence `\n` breaks, strips Korean lesson-script speaker tags (`T\t`, `S\t`), and removes standalone page numbers.
* **The "Why":** Standard PDF extractors like `fitz` preserve visual line breaks. Unstitched breaks destroy spaCy dependency trees and corrupt KeyBERT's n-gram extraction. Furthermore, administrative metadata pushed into the BM25S scoring engine degrades the confidence scores of actual learning content.
* **How to modify:** Add keywords to `_BOILERPLATE_PATTERN`. The newline stitching regex `(?<=[a-z,\-])\n(?!\n)` utilizes a negative lookahead to explicitly protect structural `\n\n` paragraph breaks.

### Layer 2: Dynamic Language Gating
* **Where:** `local_evaluator.py` -> `is_target_language()`
* **What it does:** A three-stage gate: (1) Unicode range hard-reject for CJK/Hangul (active only if target language is English), (2) Garbled-text detector for bad PDF kerning, (3) `langdetect` probabilistic check.
* **The "Why":** Bilingual textbooks interleave native-language teacher instructions with target-language content. If non-English text hits the NLP engines, spaCy misparses it, resulting in false-positive question matches and garbled expression candidates. 
* **How to modify:** The target language is currently defined locally as `target_lang_code = "en"`. For AWS deployment, this must be dynamically injected from Ednoda's Course/Lesson metadata.

### Layer 3: Imperative Filter (Dialogue Protected)
* **Where:** `labeller.py` -> `NLULabeller._is_imperative()`
* **What it does:** Drops sentences where the syntactic ROOT is a base-form verb (`TAG=VB`) with no subject (`nsubj`), *unless* the sentence contains quotation marks.
* **The "Why":** Teacher manuals are filled with operational commands (*"Read the text aloud"*, *"Check the answers"*). This filter eliminates those administrative commands while protecting narrative dialogue (*Captain Grace yelled, "Secure the ropes!"*) from being falsely flagged.
* **How to modify:** Adjust the spaCy POS tags or dependency labels. Note: This filter is applied to the Question tier, but **intentionally bypassed** for the Grammar tier, as imperatives are valid ESL structures.

### Layer 4: Additive Grammar Tier (Confidence: 0.80)
* **Where:** `labeller.py` -> `_extract_grammar_candidates()`
* **What it does:** Uses 29 specific spaCy `DependencyMatcher` templates to identify complex pedagogical sentences (e.g., Present Continuous, Modals, Comparatives).
* **The "Why":** This acts as a highlighter, not an eraser. When a sentence matches a grammar pattern, it is copied into the 0.80 Grammar Tier, but the raw text block is left completely intact. This additive approach guarantees that downstream dense embedding models (KeyBERT) can still scan the full context for multi-word expressions.

### Layer 5: Dynamic Lexical Anchoring (Confidence: 0.95)
* **Where:** `data/lexical_targets.txt` -> `NLULabeller`
* **What it does:** Words found in the target document that match the anchor list completely bypass KeyBERT/BM25S scoring thresholds and are instantly promoted to the 0.95 confidence tier.
* **The "Why":** Standard statistical models (like BM25 IDF) inherently penalize highly common words. In ESL contexts, common words (like "apple" or "run") are often the most vital pedagogical targets. The anchor overrides statistics with curriculum intent.
* **How to modify:** Edit `data/lexical_targets.txt`. No code deployment required.

## Part 2: Pipeline Data Flow

```text
Source Document (PDF / DOCX / PPTX / CSV / TXT)
        |
        v
extract_text()              | PyMuPDF / python-docx / csv
        |
        |-> data/raw_dumps/ (unmodified extractor output for debugging)
        |
        v
TextCleaner.clean()         | Removes boilerplate, stitches newlines, strips speaker tags
        |
        v
_split_sentences()          | spaCy en_core_web_sm -> fallback to ". " split
        |
        v
Language Gate               | Drops non-target language text (CJK/Hangul hard-reject + langdetect)
        |
        v
SlidingWindowChunker        | Generates 200-word overlapping chunks for context retention
        |
        v
NLULabeller
  |-- _score_bm25s()                 | Cross-chunk term scoring (IDF)
  |-- _score_keybert()               | all-MiniLM-L6-v2 dense embeddings
  |-- lexical_anchor_check           | Bypasses scoring for known curriculum targets (0.95)
  |-- _extract_grammar_candidates()  | 29 spaCy Dependency templates (0.80)
  |-- _detect_questions()            | Interrogative pattern match + Imperative filter (0.60)
  |__ deduplicate + sort
        |
        v
JSON Tier Mapping           | Outputs candidates structured by confidence thresholds