# External candidate extraction contract (task 5.10)

Defined **2026-05-20** on branch `feature/source-documents`.

## Purpose

After text extraction reaches `ready` (or `partial` in Full MVP), **candidate extraction** reads the candidate-type-free S3 text package and returns normalized **node candidate rows** with `candidateType` for teacher review. This document is the **Full external-team handoff contract** for input/output v1.

**Boundary index:** [source-document-data-contract-boundaries.md](./source-document-data-contract-boundaries.md)

Ednoda owns validation, signed callbacks, persistence, and conversion to EducationNode records. The external Python team owns extraction heuristics, model inference, and internal processing.

**Canonical Zod schemas:**

| Export | File |
| --- | --- |
| `sourceDocumentCandidateExtractionInputV1Schema` | `src/schemas/source-documents/source-document-candidate-extraction.ts` |
| `SourceDocumentCandidateExtractionInputV1` | same |
| `sourceDocumentCandidateExtractionOutputV1Schema` | same |
| `SourceDocumentCandidateExtractionOutputV1` | same |
| `sourceDocumentCandidateExtractionOutputCandidateSchema` | same |
| `sourceDocumentNodeCandidatesCallbackSchema` | `src/schemas/source-documents/source-document-callbacks.ts` |

**Upstream text package contract:** [source-document-text-package-contract.md](./source-document-text-package-contract.md)

---

## Version literals

| Literal | Where used |
| --- | --- |
| `source-document-candidate-extraction.v1` | Handoff **input** `version` field |
| `source-document-candidate-extraction-result.v1` | **Output** and node-candidates callback `version` field |

---

## Alpha vs Full

| Mode | Owner | Notes |
| --- | --- | --- |
| **Alpha stub** | Ednoda (master plan **10.1**–**10.2**) | Deterministic heuristics over `plain.txt` / chunks; same callback schema. Not defined here. |
| **Full external handoff** | External Python team (**10.5**–**10.6**) | This document defines the contract the external team builds against. |

Alpha stub and Full external worker both POST to the same signed node-candidates callback route. Only the extraction logic differs.

**Current dispatch status:** Task **10.5** packages the v1 handoff payload; task **10.6** dispatch to UBC/external workers is **deferred** until an invocation mechanism is documented and approved. In `dev`, `staging`, and `demo`, `request-candidate-extraction` may post a local TypeScript stub callback for internal UI/testing when callback signing is configured; otherwise it returns `dispatchStatus: 'not_sent'`. No production UBC worker is invoked.

**UBC-facing integration doc:** [ubc-candidate-extraction-contract.md](./ubc-candidate-extraction-contract.md) — same v1 contract written for the UBC team (task **10.6a**).

---

## Input contract — `SourceDocumentCandidateExtractionInputV1`

Ednoda (or Step Functions `request-candidate-extraction`) delivers this payload via an agreed invocation mechanism (queue message, Lambda event, SFN task input, etc.). The payload must stay **small**: IDs, target context, S3 pointers, callback URL, and optional `taskToken` only.

### Top-level fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `version` | literal | yes | Must be `source-document-candidate-extraction.v1` |
| `environment` | enum | yes | `dev`, `staging`, `demo`, or `prod` |
| `sourceDocumentId` | positive int | yes | Postgres `SourceDocument.id` |
| `extractionId` | positive int | yes | Postgres `SourceDocumentExtraction.id` for this attempt |
| `target` | discriminated union | yes | Lesson or textbook-unit target — see below |
| `extractedTextPackage` | object | yes | S3 pointers only — see below |
| `original` | object | yes | Upload metadata (`filename`, `mimeType`, `fileExtension`) |
| `callback` | object | yes | Callback URL, signing header name, optional `taskToken` |

### `target` scope

Reuses `sourceDocumentTargetSchema`. Supported targets:

**Lesson target:**

```json
{
  "targetType": "lesson",
  "lessonId": 101,
  "defaultQuestionListId": 55
}
```

`defaultQuestionListId` is optional.

**Textbook-unit target:**

```json
{
  "targetType": "textbook_unit",
  "textbookId": 12,
  "textbookUnitId": 34
}
```

**Not supported:** root-textbook uploads (`textbookUnitId = null`). Ednoda rejects these at upload and workflow boundaries. Do not design the external worker for root-textbook targets.

### `extractedTextPackage` — S3 pointers only

The candidate extraction worker runs in **Ednoda-controlled AWS infrastructure** with least-privilege IAM read access to the private source-document text bucket. External contributors may own the extraction code, but the production credential boundary remains Ednoda-controlled. Workers fetch content from S3 using that IAM role; do not expect inline text, block arrays, or file bytes in the handoff payload. Cross-account access, presigned URL handoff, and external credential distribution are out of scope for MVP.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `manifest` | `{ bucket, key }` | yes | Pointer to `manifest.json` — see text package contract |
| `plainText` | `{ bucket, key }` | yes | Pointer to `plain.txt` |
| `chunksPrefix` | `{ bucket, prefix }` | no | Prefix for `chunks/chunk-*.json` files |
| `blocksPrefix` | `{ bucket, prefix }` | no | Prefix for `blocks/block-*.json` files |

Key layout, manifest shape, block/chunk file formats, and write ordering are defined in [source-document-text-package-contract.md](./source-document-text-package-contract.md).

**Server helper for expected keys:** `src/utils/server/source-document/buildSourceDocumentExtractionTextPackageKeysUtil.ts`

### `callback`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `url` | URL string | yes | `POST /api/source-documents/node-candidates/callback` on the Ednoda app |
| `signingHeader` | literal | yes | Must be `X-Ednoda-Signature` |
| `taskToken` | string or null | no | Step Functions task token when invoked from SFN; omit or null otherwise |

### Input example

```json
{
  "version": "source-document-candidate-extraction.v1",
  "environment": "dev",
  "sourceDocumentId": 42,
  "extractionId": 7,
  "target": {
    "targetType": "lesson",
    "lessonId": 101,
    "defaultQuestionListId": 55
  },
  "extractedTextPackage": {
    "manifest": {
      "bucket": "ednoda-dev-source-document-text",
      "key": "source-document-text/user/…/document/42/extraction/7/manifest.json"
    },
    "plainText": {
      "bucket": "ednoda-dev-source-document-text",
      "key": "source-document-text/user/…/document/42/extraction/7/plain.txt"
    },
    "chunksPrefix": {
      "bucket": "ednoda-dev-source-document-text",
      "prefix": "source-document-text/user/…/document/42/extraction/7/chunks/"
    },
    "blocksPrefix": {
      "bucket": "ednoda-dev-source-document-text",
      "prefix": "source-document-text/user/…/document/42/extraction/7/blocks/"
    }
  },
  "original": {
    "filename": "lesson-vocab.txt",
    "mimeType": "text/plain",
    "fileExtension": ".txt"
  },
  "callback": {
    "url": "https://app.example.com/api/source-documents/node-candidates/callback",
    "signingHeader": "X-Ednoda-Signature",
    "taskToken": "AQCEAAAAKgAAA…"
  }
}
```

---

## Output contract — `SourceDocumentCandidateExtractionOutputV1`

The external worker POSTs the result to `callback.url`. The body must match `sourceDocumentNodeCandidatesCallbackSchema`, which extends the output v1 shape with optional idempotency fields from `sourceDocumentCallbackBaseSchema`.

### Top-level fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `version` | literal | yes | Must be `source-document-candidate-extraction-result.v1` |
| `sourceDocumentId` | positive int | yes | Must match input |
| `extractionId` | positive int | yes | Must match input |
| `status` | enum | yes | `ready`, `partial`, or `failed` |
| `candidates` | array | yes | May be empty on any status; see status rules |
| `warnings` | string[] | no | Non-fatal quality or truncation notes |
| `error` | object | conditional | Required when `status` is `failed`; must be omitted otherwise |
| `taskToken` | string or null | no | Echo input `callback.taskToken` when present |
| `workflowExecutionArn` | string | no | SFN execution ARN when known |
| `workflowExecutionRowId` | positive int | no | Postgres workflow row ID when known |
| `attemptNumber` | positive int | no | Retry attempt when known |
| `occurredAtIso` | ISO datetime | no | Worker completion timestamp |

### Status values

| Status | Meaning | `error` | `candidates` |
| --- | --- | --- | --- |
| `ready` | Candidate extraction completed normally | Must be omitted | Zero or more — an empty array is valid when no useful candidates were found |
| `partial` | Completed with non-fatal degradation (truncation, skipped sections, worker limits, low-confidence skips) | Must be omitted | Zero or more; use `warnings` |
| `failed` | Candidate extraction could not complete | **Required** | Usually empty |

### Error object shape

When `status` is `failed`, `error` is required:

```json
{
  "code": "candidate_extraction_timeout",
  "message": "Processing exceeded MAX_PROCESSING_SECONDS",
  "details": { "limitSeconds": 120 }
}
```

`details` is optional. For `ready` and `partial`, do **not** include `error`.

---

## Candidate rows — `SourceDocumentCandidateExtractionOutputCandidate`

Each candidate is a **metadata row** for review — not a rewrite of the text package. Keep callback payloads small.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `candidateType` | enum | yes | Must be an Ednoda `NodeCandidateType` value — see below |
| `text` | string (min 1) | yes | Display text for review UI |
| `normalizedText` | string or null | no | Dedupe / matching key; Ednoda prefers this for upsert when set |
| `sourceBlockId` | string or null | no | e.g. `block-000001` — links to S3 block file |
| `sourcePageNumber` | positive int or null | no | PDF page when known |
| `sourceSlideNumber` | positive int or null | no | PPTX slide when known |
| `confidence` | number 0–1 or null | no | Model confidence when applicable |
| `metadata` | object or null | no | Worker-owned JSON; Ednoda stores as `metadataJson` |

### `candidateType` values (MVP)

External workers should emit **only** these enum strings (`nodeCandidateTypeSchema`):

| Value | Typical use |
| --- | --- |
| `vocab` | Word / term entries (≤ 3 words) |
| `expression` | Phrases, collocations, and other non-question content |
| `question` | Assessment prompts |
| `unknown` | Uncertain classification |

**Invalid values:** Callback ingress rejects any `candidateType` outside the four values above (strict Zod enum). Original-PRD drift listed broader labels (`answer`, `grammar_pattern`, `phonics`, `dialogue`, `sentence_frame`, `activity_instruction`); classify that content as `expression` or `unknown` instead — they are not accepted at runtime.

**Conversion caveat:** `candidateType` maps 1:1 to atomic `EducationNode.nodeType` (`vocab`, `expression`, `question`). Composite Q&A, dialogue, and phonics node types exist in the DB but are not product-supported; candidate conversion creates atomic nodes only (master plan **2.10** / **13.2**).

**Traceability:** Prefer setting `sourceBlockId`, `sourcePageNumber`, or `sourceSlideNumber` when the candidate maps to a specific block in the S3 text package. One block may yield multiple candidates (e.g. several vocabulary items in one paragraph block).

---

## Callback signing and delivery

**Route:** `POST /api/source-documents/node-candidates/callback`

**Auth:** HMAC-SHA256 over the **raw JSON request body** (UTF-8), sent in the `X-Ednoda-Signature` header as a lowercase hex digest.

```
signature = HMAC-SHA256(SOURCE_DOCUMENT_CALLBACK_SECRET, rawBody).hex()
```

- Sign the exact bytes you POST; do not re-serialize after signing.
- Ednoda verifies with `verifySourceDocumentCallbackSignatureUtil`.
- In production, missing or invalid signatures return `401 Unauthorized`.
- Shared secret: `SOURCE_DOCUMENT_CALLBACK_SECRET` (provisioned per environment).

**Payload boundary:** Return **metadata and candidate rows only**. Do not embed:

- Full `plain.txt` body
- Block or chunk file contents
- Manifest JSON blobs
- Original file bytes
- Large base64 payloads

Workers read large content from S3; callbacks carry normalized candidate summaries only.

---

## Idempotency expectations

Ednoda treats duplicate callbacks as safe:

- **Replay:** Sending the same terminal callback again is acknowledged; converted candidates are **not overwritten**.
- **Upsert key** (same `sourceDocumentId` + `extractionId` only; no cross-document dedupe):
  1. `candidateType + sourceBlockId + normalizedText` when both `sourceBlockId` and `normalizedText` are set
  2. `candidateType + sourceBlockId + text` when `sourceBlockId` is set but `normalizedText` is not
  3. `candidateType + normalizedText` when no `sourceBlockId`
  4. `candidateType + text` as final fallback
- **Converted rows preserved:** If a candidate was already converted to an EducationNode (`convertedAt`, `educationNodeId`, `lessonNodeId`, or `textbookNodeId` set), later callbacks skip updates for that row.
- **Deleted documents:** If the source document is soft-deleted or `deletionRequestedAt` is set, the callback is acknowledged (`200`) without persisting candidates or resurrecting document status (master plan **5.9**).
- **Missing documents:** Unknown `sourceDocumentId` is acknowledged without writes.

When `callback.taskToken` is present, Ednoda **always** resolves the Step Functions task exactly once after signature validation and idempotency checks:

- `ready` / `partial` / `failed` after a successful DB update (failure uses SFN task failure when `status` is `failed`)
- Deleted document: task success with `{ "status": "skipped", "reason": "source_document_deleted" }` — no DB writes
- Missing document: task success with `{ "status": "skipped", "reason": "source_document_not_found" }` — no DB writes

Stale duplicate callbacks (same terminal state already recorded) do not re-send task completion.

---

## Output examples

### Successful `ready` with zero candidates

```json
{
  "version": "source-document-candidate-extraction-result.v1",
  "sourceDocumentId": 42,
  "extractionId": 7,
  "status": "ready",
  "candidates": [],
  "warnings": ["no_candidates_found"]
}
```

### Successful `ready` with one candidate

```json
{
  "version": "source-document-candidate-extraction-result.v1",
  "sourceDocumentId": 42,
  "extractionId": 7,
  "status": "ready",
  "candidates": [
    {
      "candidateType": "vocab",
      "text": "past tense",
      "normalizedText": "past tense",
      "sourceBlockId": "block-000003",
      "sourcePageNumber": 2,
      "confidence": 0.91,
      "metadata": { "language": "en" }
    }
  ],
  "taskToken": "AQCEAAAAKgAAA…"
}
```

### `partial` with warnings

```json
{
  "version": "source-document-candidate-extraction-result.v1",
  "sourceDocumentId": 42,
  "extractionId": 7,
  "status": "partial",
  "candidates": [
    {
      "candidateType": "question",
      "text": "What is the past tense of \"go\"?",
      "normalizedText": "what is the past tense of go",
      "sourceBlockId": "block-000001"
    }
  ],
  "warnings": ["skipped_low_confidence_blocks: 3"],
  "taskToken": null
}
```

### `failed` with error

```json
{
  "version": "source-document-candidate-extraction-result.v1",
  "sourceDocumentId": 42,
  "extractionId": 7,
  "status": "failed",
  "candidates": [],
  "error": {
    "code": "manifest_unreadable",
    "message": "Could not parse manifest.json from S3"
  },
  "taskToken": "AQCEAAAAKgAAA…"
}
```

---

## Boundaries and negative scope

| Rule | Detail |
| --- | --- |
| No root-textbook uploads | `textbookUnitId` must be set for textbook targets |
| No Postgres block table | Block metadata lives in S3 only — **do not create `SourceDocumentExtractedBlock`** |
| No inline large payloads | Input, output, and callbacks carry S3 pointers and candidate metadata only |
| No SQS as workflow coordinator | Step Functions remains the orchestrator; invocation mechanism for handoff is agreed separately (**10.6**) |
| Handoff only after text extraction | Do not run candidate extraction when text extraction is `failed` or `ocr_required` |
| Ednoda persists candidates | External worker POSTs callback; Ednoda writes `SourceDocumentNodeCandidate` rows |

This document does **not** cover: queue/SFN invocation wiring (**10.5**), Alpha stub implementation (**10.1**), callback route code (**5.4**), or EducationNode conversion (**2.11**).

---

## Related documents

| Document | Role |
| --- | --- |
| [source-document-text-package-contract.md](./source-document-text-package-contract.md) | S3 text package layout, manifest/block/chunk formats, extraction callback boundary |
| [aws-infrastructure-plan.md](./aws-infrastructure-plan.md) | Buckets, IAM, worker responsibilities |
| [server-action-plan.md](./server-action-plan.md) | App-side action boundaries |
| [master-plan.md](../master-plan.md) | Task **5.10** (this doc), **10.1** (Alpha stub), **10.5**–**10.6** (Full handoff) |
| [prompt-2.7](../prompts/prompt-2.7-source-document-candidate-extraction-contracts.md) | Schema implementation prompt |
