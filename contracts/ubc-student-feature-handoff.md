# UBC student handoff: text extraction and education-node candidates

This document explains the two pieces of logic UBC students need to understand.
It is intentionally plain. Think of the whole system like an assembly line:

1. A teacher uploads a document.
2. Ednoda turns the document into a predictable text package.
3. A candidate extractor reads that text package and suggests useful learning items.
4. The teacher reviews those suggestions.
5. Ednoda converts approved suggestions into real `EducationNode` records.

The UBC work is about steps 2 and 3 only.

## The two jobs

### Job 1: document text extraction

**Goal:** take many file types and turn them into the same shape every time.

Input:

- Original file in S3
- File metadata such as MIME type, extension, size, and owner

Output:

- `plain.txt`: all extracted text in one simple text file
- `blocks/*.json`: smaller document pieces, such as paragraphs, table rows, slides, or pages
- `chunks/*.json`: text grouped into chunks for downstream processing
- `manifest.json`: an index that points to all of the above

Important rule: text extraction does **not** decide whether text is vocab, a question, or an expression. It only describes document structure.

### Job 2: education-node candidate extraction

**Goal:** read the predictable text package and suggest possible Ednoda content.

Input:

- S3 pointers to `manifest.json`, `plain.txt`, `blocks/`, and `chunks/`
- Target context: lesson or textbook unit
- Callback URL for returning results to Ednoda

Output:

- Candidate rows with `candidateType`
- Allowed candidate types: `vocab`, `expression`, `question`, `unknown`

Important rule: candidate extraction is the first place that assigns `candidateType`.

## Main files

### Workflow wiring

| File | What it controls |
| --- | --- |
| `infra/lib/constructs/source-document-state-machine.ts` | Step Functions order: validate upload, malware gate, preview, text extraction, candidate handoff, finalize |
| `src/utils/server/source-document/startSourceDocumentWorkflowUtil.ts` | Builds the workflow input from a `SourceDocument` row |
| `lambda/source-documents/request-candidate-extraction.ts` | Builds the candidate extraction handoff after text extraction succeeds |
| `lambda/source-documents/shared/build-candidate-extraction-handoff.ts` | Creates the exact UBC-facing input payload |

### Text extraction worker

| File | What it controls |
| --- | --- |
| `workers/source-documents/text-extractor/handler.py` | Lambda entrypoint and traffic controller |
| `workers/source-documents/text-extractor/txt_logic.py` | TXT decoding, paragraph blocks, chunks |
| `workers/source-documents/text-extractor/pdf_logic.py` | PDF embedded text extraction; returns `ocr_required` when text layer is poor |
| `workers/source-documents/text-extractor/csv_logic.py` | CSV rows into table header/table row blocks |
| `workers/source-documents/text-extractor/docx_logic.py` | DOCX XML parsing into paragraph, heading, and table blocks |
| `workers/source-documents/text-extractor/pptx_logic.py` | PPTX XML parsing into slide and speaker-note blocks |
| `workers/source-documents/text-extractor/extraction_limits.py` | Caps chars, blocks, and chunks; can mark output `partial` |
| `workers/source-documents/text-extractor/package_writer.py` | Writes `plain.txt`, block files, chunk files, and `manifest.json` |

### Shared worker contracts

| File | What it controls |
| --- | --- |
| `workers/source-documents/shared/event.py` | Parses Lambda events into Python dataclasses |
| `workers/source-documents/shared/contracts.py` | Shared literal strings: statuses, versions, strategies, warnings |
| `workers/source-documents/shared/keys.py` | Predictable S3 key layout |
| `workers/source-documents/shared/callback_post.py` | Builds and signs callbacks back to Ednoda |
| `workers/source-documents/shared/ubc_input.py` | Python parser for the UBC handoff input |

### Candidate extraction worker/stub

| File | What it controls |
| --- | --- |
| `workers/source-documents/candidate-extractor-stub/handler.py` | Current deterministic candidate extractor entrypoint |
| `workers/source-documents/candidate-extractor-stub/heuristics.py` | Simple rules that find vocab/questions/expressions from plain text |
| `workers/source-documents/candidate-extractor-stub/ubc_local_adapter.py` | Local harness for the future UBC boundary |
| `lambda/source-documents/shared/dispatch-dev-candidate-stub.ts` | TypeScript mirror used by dev/staging/demo Step Functions |

### Ednoda callback and persistence

| File | What it controls |
| --- | --- |
| `src/app/api/source-documents/extraction/callback/route.ts` | HTTP endpoint for text extraction callbacks |
| `src/utils/server/source-document/completeSourceDocumentExtractionCallbackUtil.ts` | Saves extraction status and S3 pointers to Postgres |
| `src/app/api/source-documents/node-candidates/callback/route.ts` | HTTP endpoint for candidate extraction callbacks |
| `src/utils/server/source-document/completeSourceDocumentNodeCandidatesCallbackUtil.ts` | Upserts candidate rows from callback payload |
| `src/utils/server/source-document/convertSourceDocumentCandidateUtil.ts` | Converts reviewed candidates into `EducationNode` plus lesson/textbook links |

### Canonical TypeScript schemas

| File | What it controls |
| --- | --- |
| `src/schemas/source-documents/source-document-text-package.ts` | Manifest, block, workflow input schemas |
| `src/schemas/source-documents/source-document-candidate-extraction.ts` | UBC handoff input and candidate output schemas |
| `src/schemas/source-documents/source-document-callbacks.ts` | Worker callback schemas |
| `src/schemas/source-documents/source-document-enums.ts` | Statuses, strategies, and allowed candidate types |

## How text extraction works

Step by step:

1. Step Functions invokes `workers/source-documents/text-extractor/handler.py`.
2. `handler.py` parses the event with `parse_text_extractor_event`.
3. It reads the original upload from S3.
4. It checks that the file bytes match the declared file type.
5. It chooses the right extraction module:
   - `.txt` -> `txt_logic.py`
   - `.pdf` -> `pdf_logic.py`
   - `.csv` -> `csv_logic.py`
   - `.docx` -> `docx_logic.py`
   - `.pptx` -> `pptx_logic.py`
6. The file-specific module returns:
   - `plain_text`
   - `blocks`
   - `chunks`
   - counts and warnings
7. `extraction_limits.py` trims output if needed.
8. `package_writer.py` writes S3 artifacts.
9. The worker posts a signed callback to `/api/source-documents/extraction/callback`.
10. Ednoda saves the result in `SourceDocumentExtraction` and updates the parent `SourceDocument`.

The predictable S3 key pattern is:

```plain text
source-document-text/user/{ownerUserId}/document/{sourceDocumentId}/extraction/{extractionId}/
```

Inside that folder:

```plain text
plain.txt
manifest.json
blocks/block-000001.json
chunks/chunk-000001.json
```

## What a block is

A block is one piece of the document.

Examples:

- A TXT paragraph
- A PDF page of text
- A CSV table row
- A DOCX paragraph or table
- A PPTX slide or speaker note

Blocks have IDs like `block-000001`.

## What a chunk is

A chunk is a group of one or more blocks, usually near a target character size.

Chunks exist because downstream candidate extraction may not want to process one giant text file at once. Chunks have IDs like `chunk-000001`.

## What the manifest is

`manifest.json` is the table of contents for the extracted text package.

It says:

- Which source document this came from
- Which extraction attempt created it
- What strategy was used, such as `plain_text`, `pdf_text_layer`, `docx`, `pptx`, or `csv`
- How many chars, blocks, and chunks exist
- Where `plain.txt`, block files, and chunk files live in S3

The manifest should not contain the whole text body. Large text stays in separate S3 files.

## How candidate extraction works today

There are two current paths to understand:

1. `workers/source-documents/candidate-extractor-stub/handler.py`
   - Reads `plain.txt` from S3.
   - Runs deterministic Python heuristics.
   - Posts a signed node-candidates callback.
   - Useful as a real heuristic reference, but not the currently wired Step Functions stub path.

2. `lambda/source-documents/request-candidate-extraction.ts`
   - Builds the official UBC handoff payload.
   - In `dev`, `staging`, and `demo`, it may dispatch a local TypeScript stub that posts dummy candidates when callback signing is configured.
   - For real UBC/external dispatch, the production mechanism is still deferred.

The UBC handoff payload is versioned:

```plain text
source-document-candidate-extraction.v1
```

The candidate result callback is versioned:

```plain text
source-document-candidate-extraction-result.v1
```

## Current candidate heuristics

The current Python stub heuristics are deliberately simple:

- If a line contains `?`, it becomes a `question` candidate.
- If a line looks like `term: definition`, `term - definition`, or `term — definition`, it becomes a `vocab` candidate.
- If a short phrase repeats across multiple lines, it becomes an `expression` candidate.
- Duplicate candidates are removed by `candidateType + normalizedText`.

This is not the final intelligence. It is a stable placeholder so Ednoda can build UI and callbacks before UBC supplies stronger extraction logic.

The TypeScript local stub used by the `dev` / `staging` / `demo` Step Functions path is even simpler: it creates deterministic dummy candidates from the handoff metadata and does **not** read S3. UBC should treat the Python heuristics and the v1 contract as the useful implementation references, not the dummy TypeScript output quality.

## How candidate callbacks become database rows

1. Candidate worker posts to `/api/source-documents/node-candidates/callback`.
2. Ednoda verifies `X-Ednoda-Signature`.
3. Ednoda validates the JSON with Zod.
4. `completeSourceDocumentNodeCandidatesCallbackUtil.ts` finds the matching extraction attempt.
5. It upserts `SourceDocumentNodeCandidate` rows.
6. It does not overwrite candidates that were already converted.
7. The teacher reviews candidates in the UI.

## How candidates become EducationNodes

Conversion is Ednoda-owned, not UBC-owned.

`convertSourceDocumentCandidateUtil.ts` maps:

- `vocab` -> `EducationNode.nodeType = vocab`
- `expression` -> `EducationNode.nodeType = expression`
- `question` -> `EducationNode.nodeType = question`
- `unknown` -> not convertible until the teacher edits the type

Then Ednoda links the node:

- Lesson upload -> `LessonNode`
- Textbook-unit upload -> `TextbookNode`

UBC should return good candidate rows. Ednoda handles final conversion.

## What UBC should focus on

For text extraction:

- Make `plain.txt` useful and readable.
- Make blocks stable and traceable.
- Preserve source location when possible, such as page number or slide number.
- Keep output candidate-type-free.
- Add tests for every supported file type.

For candidate extraction:

- Read the v1 handoff payload.
- Load `plain.txt`, and optionally load `manifest.json`, blocks, and chunks.
- Return candidates using only `vocab`, `expression`, `question`, or `unknown`.
- Include useful `normalizedText` for dedupe.
- Include `sourceBlockId`, `sourcePageNumber`, or `sourceSlideNumber` when possible.
- Keep callback payloads small.
- Sign the callback with `X-Ednoda-Signature`.

## Things UBC should not do

- Do not create `EducationNode` records directly.
- Do not write to Postgres directly.
- Do not bypass Ednoda callback routes.
- Do not put candidate types into text extraction output.
- Do not send the whole document text inside callback JSON.
- Do not invent new candidate types without changing the shared enum and schema first.

## Readiness recommendation

The **contract shape is the right decision** for MVP:

- one `plain.txt`
- many `blocks/*.json`
- many `chunks/*.json`
- one `manifest.json`

This is a good boundary because every file type becomes one common package. Candidate extraction can then ignore whether the original was PDF, DOCX, PPTX, TXT, or CSV.

The current implementation is **MVP-transition-ready**, not "all classroom documents are handled well" ready.

It should work as a starting point for:

- plain text files
- simple CSV vocabulary lists
- simple DOCX files with normal paragraphs and tables
- simple PPTX decks with real text boxes
- PDFs that already have an embedded text layer

It will be weaker for:

- scanned PDFs
- photographed textbook pages
- worksheets where layout matters
- quizzes with answer keys in separate columns or pages
- teacher guides with sidebars, standards, notes, and answer sections
- PPTX files where slide order, notes, title/body hierarchy, or tables matter

For a solid MVP handoff, UBC should spend some time refining text extraction, but not forever. The best path is:

1. First lock the contract and write tests around it.
2. Then improve extraction quality for the highest-value classroom document types.
3. Then build candidate extraction against the stable package.

Bad extracted text creates bad candidates. But perfect extraction is not required before candidate extraction can start.

## Known extraction gaps to discuss

These are good UBC collaboration topics:

- **OCR:** image-only PDFs currently become `ocr_required`; many real textbook pages and worksheets may need OCR.
- **Tables:** CSV and DOCX tables are mostly flattened to text. Candidate extraction may need structured rows for vocab lists and quizzes.
- **PPTX source location:** slide text should preserve slide number clearly, not look like a page number.
- **Layout:** sidebars, headings, questions, answer keys, and columns can be important. Plain text alone loses some of this.
- **Language detection:** current extraction mostly marks non-empty text as English. Korean and mixed-language documents need better detection.
- **Partial output consistency:** if output is truncated by character/block/chunk limits, `plain.txt`, blocks, chunks, and manifest counts must stay consistent.
- **Golden fixtures:** the team needs a small set of real-ish sample documents and expected outputs.

## Is the S3 package enough for candidate extraction?

Yes, for MVP, if the package is consistent.

The candidate extractor should usually start with:

- `manifest.json` to understand the document and find files
- `plain.txt` for simple global extraction
- `chunks/*.json` for model-sized extraction passes
- `blocks/*.json` when source location or structure matters

For better candidate quality, UBC should use blocks and chunks, not only `plain.txt`.

Examples:

- For a textbook page, blocks help tie candidates back to a page.
- For a PPTX deck, blocks help tie candidates back to a slide.
- For a CSV vocab list, structured table rows would help detect term/definition pairs.
- For a quiz, blocks may help separate questions from answer choices or answer keys.

## Questions for tomorrow

1. Should UBC own improvements to file-specific text extraction, candidate extraction, or both?
2. Will UBC run inside Ednoda AWS as Lambda/container code, or will Ednoda invoke an external service?
3. Should UBC use only `plain.txt`, or also inspect `manifest.json`, blocks, and chunks?
4. What confidence score means "good enough to show the teacher"?
5. How should UBC handle Korean, mixed-language documents, and low-quality PDFs that need OCR?
6. What examples should become the shared test set?

## Small mental model

Text extraction says:

> "Here is exactly what text was in the document, split into useful pieces."

Candidate extraction says:

> "From that text, here are possible things a teacher might want to teach."

Ednoda conversion says:

> "The teacher approved this suggestion, so now it becomes real Ednoda content."

For tomorrow's handoff, "education-node extraction" should mean **candidate extraction from the text package**. UBC should produce candidate rows that can later become `EducationNode` records after teacher review. UBC should not write `EducationNode`, `LessonNode`, or `TextbookNode` records directly.

## Recommended handoff package

Because UBC should not have access to the full Ednoda repo, use a **small external handoff repo**.

Keep it boring and narrow. The UBC repo should contain only the two worker concerns:

1. document text extraction
2. candidate extraction from the text package

It should not contain the Ednoda app, database models, UI, auth, server actions, or CDK stack.

Recommended repo shape:

```plain text
ednoda-source-document-workers/
  README.md
  contracts/
    text-package-v1.md
    candidate-extraction-v1.md
    examples/
      manifest.example.json
      block.example.json
      chunk.example.json
      candidate-result.example.json
  extraction/
    handler.py
    txt_logic.py
    pdf_logic.py
    csv_logic.py
    docx_logic.py
    pptx_logic.py
    package_writer.py
    tests/
  candidate_extraction/
    handler.py
    heuristics.py
    tests/
  shared/
    contracts.py
    event.py
    keys.py
    ubc_input.py
  fixtures/
    input_documents/
    expected_text_packages/
    expected_candidates/
  scripts/
    run_extract_local.py
    run_candidates_local.py
```

For the handoff, provide:

- this document
- `source-document-text-package-contract.md`
- `source-document-candidate-extraction-contract.md`
- `ubc-candidate-extraction-contract.md`
- the worker folders under `workers/source-documents/`
- the handoff Lambda files under `lambda/source-documents/`
- a small fixture set of sample documents
- expected output examples for `manifest.json`, `plain.txt`, blocks, chunks, and candidates
- one local command that runs extraction on a sample file
- one local command that runs candidate extraction on a sample package

For a three-week project, do **not** start with independent AWS deployment unless the team already has that working. The simplest plan is:

1. UBC works in the small external repo.
2. UBC proves behavior with local tests and fixtures.
3. Ednoda reviews the final worker code and test outputs.
4. Ednoda copies/replaces the implementation inside this repo.
5. Later, if needed, Ednoda can turn that worker repo into its own CI/deployment unit.

The biggest danger is contract drift. To avoid that, freeze the v1 input/output contracts for the three-week project and only allow changes by explicit agreement.
