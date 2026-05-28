# Working Agreement

This repository is a handoff snapshot for UBC source-document worker work.
It is not the production Ednoda app repository.

## What to Change

UBC work should stay inside:

- `workers/text-extractor/`
- `workers/candidate-extractor-stub/`
- `workers/shared/`
- `contracts/`
- `scripts/`
- `fixtures/input-documents/`

The main ownership boundaries are:

- Text extraction produces `plain.txt`, `blocks/*.json`, `chunks/*.json`, and `manifest.json`.
- Text extraction must not assign `candidateType`.
- Candidate extraction is the first step that assigns `vocab`, `expression`, `question`, or `unknown`.
- UBC should not write Ednoda database rows or create `EducationNode` records directly.

## Before Sending Changes Back

Run the local smoke checks:

```bash
python scripts/run_text_extraction_local.py fixtures/input-documents/alpha-lesson-notes.txt
python scripts/run_text_extraction_local.py fixtures/input-documents/full-vocabulary.csv
python scripts/run_text_extraction_local.py fixtures/input-documents/full-lesson-document.docx
python scripts/run_text_extraction_local.py fixtures/input-documents/full-lesson-slides.pptx
python scripts/run_text_extraction_local.py fixtures/input-documents/alpha-embedded-text-lesson.pdf
```

Then run candidate extraction against one generated `plain.txt`:

```bash
python scripts/run_candidate_extraction_local.py \
  local-output/text-alpha-notes/source-document-text/user/00000000-0000-4000-8000-000000000001/document/42/extraction/7/plain.txt \
  --output local-output/text-alpha-notes/candidate-result.json
```

`local-output/`, `__pycache__/`, and `.pytest_cache/` are generated artifacts and should not be committed.

## Secrets and Access

Do not add credentials, tokens, production bucket names with real access keys, or private student/teacher data.
This package is designed to work locally without AWS credentials.

## Sync Policy

Treat this repository as a snapshot. When Ednoda changes the source-document contracts, Ednoda will refresh this handoff intentionally rather than expecting automatic sync from the main app repo.
