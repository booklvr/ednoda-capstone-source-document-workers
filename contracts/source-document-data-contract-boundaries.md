# Source Document data contract boundaries (task 10.6g)

Defined **2026-05-20** on branch `feature/source-documents`.

## Purpose

Lock the separation between **text extraction**, **preview**, and **candidate extraction** so future agents and the UBC team cannot confuse:

- what the text-extraction worker produces (candidate-type-free S3 packages), and
- what UBC / the local stub produces (candidate rows with `candidateType`).

This doc is the **glossary and boundary index**. Canonical field shapes live in Zod schemas and the linked contract docs below.

---

## Three separate data products

| Product | Owner | Storage | Contains `candidateType`? |
| --- | --- | --- | --- |
| **Original document** | Ednoda upload flow | Documents bucket (`original` key) | No |
| **Preview artifacts** | Preview worker | Preview bucket (pages, snippets) | No — teacher-facing visual confirmation only; independent of text extraction |
| **Extracted text package** | Text-extraction worker | Text bucket (`plain.txt`, `blocks/`, `chunks/`, `manifest.json`) | **No** |

**Candidate rows** (`SourceDocumentNodeCandidate`) are a **fourth product**, produced only by **candidate extraction** (UBC or Alpha stub), not by text extraction.

---

## Text extraction contract — what it does and does not do

**Does:**

- Convert an uploaded document (Alpha: PDF with text layer, TXT) into structured plain text.
- Write a candidate-type-free S3 text package when status is `ready`:
  - `manifest.json` (written last — completion marker)
  - `plain.txt`
  - `blocks/block-*.json`
  - `chunks/chunk-*.json`
- POST a signed extraction callback with **pointers and counts only** (no inline text bodies).
- Emit extraction status, strategy, counts, warnings, and errors.

**Does not:**

- Assign semantic content labels (`vocab`, `expression`, `question`, `unknown`).
- Emit `candidateType` or any field named like a candidate label.
- Produce node-candidate rows or POST the node-candidates callback.
- Read or depend on preview artifacts for extraction output.

Block metadata uses **`blockType`** (`paragraph`, `heading`, `table`, …) and **`importanceHint`** — these describe document structure, **not** Ednoda candidate types.

**Canonical schemas:** `src/schemas/source-documents/source-document-text-package.ts`  
**Full worker contract:** [source-document-text-package-contract.md](./source-document-text-package-contract.md)

---

## UBC / local stub handoff input — what Ednoda passes

After text extraction reaches `ready`, Ednoda builds `SourceDocumentCandidateExtractionInputV1` (task **10.5**). The payload is **compact**:

| Included | Excluded |
| --- | --- |
| IDs (`sourceDocumentId`, `extractionId`) | Inline full document text |
| Target context (lesson / textbook unit) | Original file bytes |
| Original upload metadata (`filename`, `mimeType`, `fileExtension`) | Block/chunk JSON arrays |
| S3 text package pointers (`manifest`, `plainText`, optional `blocksPrefix`, `chunksPrefix`) | Manifest JSON body |
| Callback URL, signing header, optional `taskToken` | Preview images or metadata |

UBC / stub **fetch** large content from S3 using IAM (or agreed access). Production dispatch to UBC is **deferred** (task **10.6**). In `dev`, `staging`, and `demo`, `request-candidate-extraction` may post a local TypeScript stub callback for internal UI/testing when callback signing is configured; otherwise it returns `dispatchStatus: 'not_sent'`.

**Canonical schema:** `sourceDocumentCandidateExtractionInputV1Schema` in `src/schemas/source-documents/source-document-candidate-extraction.ts`  
**UBC-facing doc:** [ubc-candidate-extraction-contract.md](./ubc-candidate-extraction-contract.md)

---

## UBC / local stub callback output — what UBC returns

Candidate extraction POSTs `sourceDocumentNodeCandidatesCallbackSchema` to `/api/source-documents/node-candidates/callback`.

**Output contains:**

- Terminal status (`ready`, `partial`, `failed`)
- **`candidates[]`** — each row includes **`candidateType`** (`vocab` | `expression` | `question` | `unknown`)
- Optional traceability (`sourceBlockId`, page/slide numbers, `confidence`, `metadata`)
- Warnings or error — **not** a rewrite of the text package

**Does not contain:** full `plain.txt`, block bodies, manifest blobs, or original file bytes.

**Canonical schemas:**

| Export | File |
| --- | --- |
| `sourceDocumentCandidateExtractionOutputV1Schema` | `source-document-candidate-extraction.ts` |
| `sourceDocumentNodeCandidatesCallbackSchema` | `source-document-callbacks.ts` |

**Internal + UBC docs:** [source-document-candidate-extraction-contract.md](./source-document-candidate-extraction-contract.md), [ubc-candidate-extraction-contract.md](./ubc-candidate-extraction-contract.md)

---

## Candidate type ownership and allowed values

| Stage | Assigns `candidateType`? | Allowed values |
| --- | --- | --- |
| Text extraction | **No** | — (must not appear in manifest, blocks, chunks, or extraction callback) |
| Preview | **No** | — |
| Candidate extraction (UBC or Alpha stub) | **Yes — first and only step** | `vocab`, `expression`, `question`, `unknown` |

**Conversion mapping** (Ednoda app, not UBC): atomic `candidateType` values map 1:1 to `EducationNode.nodeType` for `vocab`, `expression`, and `question`. `unknown` is stored for review but is not convertible until the teacher sets a concrete type.

**Taxonomy decision record:** [source-document-candidate-type-taxonomy-decision.md](./source-document-candidate-type-taxonomy-decision.md)

---

## Explicit anti-drift rules

1. **Never** describe text extraction output as containing or inferring candidate types.
2. **Never** tell UBC or workers that broad PRD labels (`answer`, `grammar_pattern`, `phonics`, `dialogue`, `sentence_frame`, `activity_instruction`) are accepted at runtime — they are **original-PRD drift**; use `expression` or `unknown`.
3. **Do not** use "legacy accepted on ingest", "deprecated but accepted", or similar language in active contracts.
4. **`answerText` / `promptText`** on candidate rows are optional **review hints** — not candidate types, not used for MVP conversion.
5. **`blockType: unknown`** in the text package means structural classification only — not `NodeCandidateType.unknown`.
6. Historical prompts that list 10 candidate types are **superseded** — see taxonomy decision and prompt headers marked after 10.6c–10.6e.

---

## Where to find canonical schemas

| Concern | Primary file |
| --- | --- |
| Shared enums (`NodeCandidateType`, extraction/preview status) | `src/schemas/source-documents/source-document-enums.ts` |
| Text package manifest, blocks, workflow input | `src/schemas/source-documents/source-document-text-package.ts` |
| Candidate handoff input/output | `src/schemas/source-documents/source-document-candidate-extraction.ts` |
| All worker callbacks | `src/schemas/source-documents/source-document-callbacks.ts` |
| Handoff payload builder (Lambda) | `lambda/source-documents/shared/build-candidate-extraction-handoff.ts` |
| Text package writer (Python) | `workers/source-documents/text-extractor/package_writer.py` |
| Candidate stub (Python) | `workers/source-documents/candidate-extractor-stub/heuristics.py` |

---

## Related tasks

| Task | Role |
| --- | --- |
| 9.11 | Text package handoff readiness — [ubc-text-package-handoff-readiness.md](./ubc-text-package-handoff-readiness.md) |
| 10.6a | UBC candidate contract — [ubc-candidate-extraction-contract.md](./ubc-candidate-extraction-contract.md) |
| 10.6c–10.6f | Candidate type taxonomy cleanup |
| **10.6g (this doc)** | Data contract clarity lock |
| 10.6 | UBC dispatch — deferred |

**Recommended next task:** **10.6b** (local UBC adapter/stub harness) or **16.1** (browser Alpha smoke test), depending on team priority.
