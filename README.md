# Ednoda Source Document Workers Handoff

This is a small, scoped copy of the Ednoda source-document worker boundary for UBC student work.

It intentionally contains only the code and contracts needed for:

1. document text extraction
2. candidate extraction from the extracted text package

It does **not** include the Ednoda app, auth, database models, UI, migrations, deployment stack, secrets, or production credentials.

## Work Boundary

Text extraction turns uploaded documents into a candidate-type-free text package:

```plain text
plain.txt
blocks/block-000001.json
chunks/chunk-000001.json
manifest.json
```

Candidate extraction reads that text package and returns candidate rows with:

```plain text
candidateType = vocab | expression | question | unknown
```

UBC should not write `EducationNode`, `LessonNode`, `TextbookNode`, or Postgres rows directly. Ednoda handles signed callbacks, persistence, teacher review, and final conversion.

## Important Folders

```plain text
contracts/
  UBC-facing and internal data-contract docs.

workers/text-extractor/
  Python text extraction logic for TXT, PDF, CSV, DOCX, and PPTX.

workers/candidate-extractor-stub/
  Current deterministic candidate extraction reference and local UBC adapter.

workers/shared/
  Shared Python contracts, event parsing, S3 key layout, callbacks, and limits.

lambda-contracts/
  TypeScript handoff builder and local dev/staging/demo stub reference.

typescript-schemas/
  Read-only copies of the canonical Zod schemas relevant to this boundary.

fixtures/input-documents/
  Small sample files for local testing.

scripts/
  Local runners that avoid AWS and write to local-output/.
```

## Setup

Use Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Text Extraction Locally

```bash
python scripts/run_text_extraction_local.py \
  fixtures/input-documents/alpha-lesson-notes.txt \
  --output-dir local-output/text-alpha-notes
```

For DOCX/PPTX/PDF examples:

```bash
python scripts/run_text_extraction_local.py fixtures/input-documents/full-lesson-document.docx
python scripts/run_text_extraction_local.py fixtures/input-documents/full-lesson-slides.pptx
python scripts/run_text_extraction_local.py fixtures/input-documents/alpha-embedded-text-lesson.pdf
python scripts/run_text_extraction_local.py fixtures/input-documents/full-vocabulary.csv
```

The runner writes a fake local S3 bucket layout under `local-output/`.

## Run Candidate Extraction Locally

After text extraction:

```bash
python scripts/run_candidate_extraction_local.py \
  local-output/text-alpha-notes/source-document-text/user/00000000-0000-4000-8000-000000000001/document/42/extraction/7/plain.txt \
  --output local-output/text-alpha-notes/candidate-result.json
```

The candidate runner uses the current deterministic Python heuristics. The production UBC implementation should improve this logic while keeping the v1 callback contract stable.

## Contract Rules

- Text extraction must not emit `candidateType`.
- Candidate extraction is the first place that assigns `vocab`, `expression`, `question`, or `unknown`.
- Candidate callbacks must not include full document text, block bodies, manifest blobs, original file bytes, or base64 payloads.
- `promptText` and `answerText` are optional review hints only; MVP conversion uses `text`.
- Real UBC production dispatch is deferred. Local stubs are test harnesses, not production invocation.

## Recommended First Tasks

1. Read `contracts/ubc-student-feature-handoff.md`.
2. Read `contracts/ubc-candidate-extraction-contract.md`.
3. Run the local text extraction script on all fixture files.
4. Add or improve tests before changing extraction behavior.
5. Improve candidate extraction against `manifest.json`, `plain.txt`, blocks, and chunks.
