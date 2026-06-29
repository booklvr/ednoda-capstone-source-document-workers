# Candidate Extraction Updates
*Claude was used to help with the development of the documentation and creating tests.*

## Summary 

In the first staging run, we flagged three problems on a 44-page PDF: **562
candidates**, **wrong-language candidates leaking through**, and **~300s KeyBERT
runtime**. The goal is to address each and keep the shape of what was passed in the student integration report. 

| Problem | What we did | Metric |
|---|---|---|
| Wrong-language candidates | **Token-level** language gate before scoring (config, default `en`) + strict candidate check; BM25 never sees other-language text, so it can't promote rare Korean tokens | **Measured** on the real bilingual Korean lesson doc (`3학년 지도서`): Korean candidates in output **14 → 0**; input text 88,317 → 33,467 chars (non-target/noise removed) |
| Too many candidates | Quality pruning: drop fragments, collapse inflectional/determiner near-dups; high safety ceiling (200) only as a guardrail | Quality-driven count, **≤200** hard cap. Full drop vs staging's 562 needs the same 44-page PDF in staging |
| Latency | Lazy model loading (no heavy imports at cold-start), overlap de-dup (~25% less text scored), batched KeyBERT, skip empty BM25 queries | Local end-to-end ~3.5s on the 88KB Korean doc (warm model); cold-start + the ~300s KeyBERT baseline → confirm in staging |

Measured locally with `venv` against `data/raw_dumps/` (the repo's real extracted
text). No coverage loss is a hard rule: every unique sentence is still scored
once; reduction comes from removing noise/duplicates, not from dropping content.

## Pipeline

`S3 read → preprocess (language gate + clean) → chunk → dedupe → label
(BM25+KeyBERT+spaCy) → normalize → prune → signed callback`

## Modules (single-purpose, dependency-free unless noted)

| File | Responsibility |
|---|---|
| `language_filter.py` | Token-level target-language gate + strict candidate check (drops foreign-script tokens, not whole lines); no hardcoded words — capture is language-based |
| `preprocess.py` | Compose language gate + cleaner; resolve target language from env |
| `cleaner.py` | Strip running headers/footers, page furniture, speaker tags, boilerplate |
| `chunk_dedup.py` | Collapse the chunker's sentence overlap so each sentence is scored once |
| `labeller.py` | BM25 + KeyBERT + spaCy ensemble (NLU deps loaded lazily) |
| `candidate_pruner.py` | Drop low-quality, collapse near-dups, type-balanced safety ceiling |
| `handler.py` | UBC handoff: S3 read → pipeline → normalize → prune → callback; never raises |

## Config (env vars)

| Var | Default | Purpose |
|---|---|---|
| `CANDIDATE_TARGET_LANGUAGE` | `en` | Target language to keep (config, not hardcoded) |
| `CANDIDATE_MAX_RESULTS` | `200` | Safety ceiling; `0`/empty disables |
| `KEYBERT_*`, `BM25S_*`, `*_CONFIDENCE` | see `labeller.py` | Scoring knobs |

## Changes from my last handoff

The student integration report shape was adopted as changes were made to be able to successfully push it into the staging website. So we adopted the changes so the next handoff will be smooth.

S3 block reading, `grammar → expression` normalization, compact callback return,
lazy model loading, Dockerfile (CPU torch + baked HF model), `requirements.txt`,
and the `candidate-extractor-nlu` dir name. Kept our additions on top (language
gate, dedupe, pruning, observability). `text-extractor/` was not touched.

## For considerations

1. **Volume tuning.** On the Korean doc the result hit the 200 safety ceiling —
   quality pruning alone did not reach a reasonable 10–25 target. Tune confidence
   thresholds / KeyBERT `top_n` / ceiling in staging to land a teacher-friendly
   count. (Known next-pass item, not a defect.)
2. Run on a 44-page PDF in staging to confirm runtime/candidate counts at scale
   on the deployed image (scoring path validated locally via `venv`).
3. Optionally populate the EMPTY `data/lexical_targets.txt` with a general
   curriculum wordlist (e.g. CEFR-J) — never document-specific words.
4. Decide whether to add a per-document `targetLanguage` field to the contract.

## Tests & validation

57 tests in `workers/candidate-extractor-nlu/tests/`, green under both `venv`
(real NLU deps) and dep-free system Python. Validated on real data
(`data/raw_dumps/`): on the bilingual Korean lesson doc, the **full handler**
(KeyBERT + question + grammar tiers) returned **0 Korean-containing candidates**
(was 14/16 before the token-level gate fix).
