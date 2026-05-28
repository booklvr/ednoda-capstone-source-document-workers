# UBC candidate extraction integration contract (task 10.6a)

Prepared **2026-05-20** for the UBC (external Python) team.

## Purpose

This document is the **UBC-facing integration contract** for Source Document **node candidate extraction**. It describes exactly what Ednoda will pass to UBC (candidate-type-free text package pointers), how UBC reads that package, and what UBC must POST back (candidate rows with `candidateType`).

**Boundary index:** [source-document-data-contract-boundaries.md](./source-document-data-contract-boundaries.md)

**Audience:** UBC engineers who do not need Ednoda internals. Canonical Zod schemas remain the source of truth when this doc and code disagree.

**Dispatch status:** Real UBC/external dispatch is **not active yet**. Ednoda builds the v1 handoff payload (task **10.5**). In `dev`, `staging`, and `demo`, `request-candidate-extraction` may post a local TypeScript stub callback for internal UI/testing when callback signing is configured; otherwise it returns `dispatchStatus: 'not_sent'`. Production UBC invocation remains task **10.6** after an agreed mechanism is approved.

---

## Ednoda vs UBC ownership

| Owner | Responsibilities |
| --- | --- |
| **Ednoda** | Document upload, malware gate, preview generation, text extraction, S3 text package writing, handoff payload assembly, signed callback validation, Postgres persistence, teacher review UI, conversion to Ednoda `EducationNode` content |
| **UBC** | Candidate extraction logic: read Ednoda's S3 text package, produce normalized candidate rows, POST signed callback to Ednoda |

UBC does **not** own upload, preview, text extraction, or Postgres writes. Ednoda does **not** own UBC's heuristics, models, or internal processing.

**Local stub note:** Ednoda runs deterministic candidate stubs for internal UI/testing. The Python worker stub (`workers/source-documents/candidate-extractor-stub/`) reads `plain.txt` and runs simple heuristics. The currently wired `dev` / `staging` / `demo` Step Functions path uses the TypeScript local stub mirror in `lambda/source-documents/shared/dispatch-dev-candidate-stub.ts`. Neither stub is UBC; both use the same callback schema.

---

## Prerequisites — when Ednoda invokes UBC

Candidate extraction runs only after text extraction reaches **`ready`** with a complete S3 text package. Ednoda does **not** invoke UBC when text extraction is `partial`, `failed`, or `ocr_required`.

See [ubc-text-package-handoff-readiness.md](./ubc-text-package-handoff-readiness.md) for Ednoda's verified text package layout.

---

## Version literals

| Literal | Where used |
| --- | --- |
| `source-document-candidate-extraction.v1` | Handoff **input** `version` field |
| `source-document-candidate-extraction-result.v1` | **Output** / node-candidates callback `version` field |

**Canonical schemas (Ednoda repo):**

| Export | File |
| --- | --- |
| `sourceDocumentCandidateExtractionInputV1Schema` | `src/schemas/source-documents/source-document-candidate-extraction.ts` |
| `sourceDocumentCandidateExtractionOutputV1Schema` | same |
| `sourceDocumentNodeCandidatesCallbackSchema` | `src/schemas/source-documents/source-document-callbacks.ts` |

**Upstream text package:** [source-document-text-package-contract.md](./source-document-text-package-contract.md)

**Internal mirror doc:** [source-document-candidate-extraction-contract.md](./source-document-candidate-extraction-contract.md)

---

## Input contract — what Ednoda passes to UBC

Ednoda delivers a compact JSON payload (`SourceDocumentCandidateExtractionInputV1`). The payload contains **IDs, target context, S3 pointers, callback URL, and optional Step Functions task token only**.

Ednoda does **not** pass in the handoff payload:

- Inline full document text
- Original file bytes
- Block or chunk JSON arrays
- Manifest JSON body
- Preview images or preview metadata

UBC reads large content from S3 using the pointers below.

### Top-level fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `version` | literal | yes | Must be `source-document-candidate-extraction.v1` |
| `environment` | enum | yes | `dev`, `staging`, `demo`, or `prod` |
| `sourceDocumentId` | positive int | yes | Ednoda document ID |
| `extractionId` | positive int | yes | Ednoda text extraction attempt ID |
| `target` | object | yes | Lesson or textbook-unit scope — see below |
| `extractedTextPackage` | object | yes | S3 pointers to the text package — see below |
| `original` | object | yes | Upload metadata (`filename`, `mimeType`, `fileExtension`) |
| `callback` | object | yes | Where and how UBC POSTs results — see below |

### `target` — conversion scope

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

**Not supported:** root-textbook uploads (`textbookUnitId = null`). Do not design UBC logic for that target.

### `extractedTextPackage` — S3 pointers

Each field is a bucket + key or bucket + prefix. All pointers reference the same private Ednoda text bucket for the environment (e.g. `ednoda-dev-source-document-text`).

| Field | Shape | Required | Maps to text package |
| --- | --- | --- | --- |
| `manifest` | `{ "bucket", "key" }` | yes | `manifest.json` — package index and completion marker |
| `plainText` | `{ "bucket", "key" }` | yes | `plain.txt` — full extracted plain text |
| `chunksPrefix` | `{ "bucket", "prefix" }` | no | Prefix ending in `chunks/` for `chunk-*.json` files |
| `blocksPrefix` | `{ "bucket", "prefix" }` | no | Prefix ending in `blocks/` for `block-*.json` files |

**Typical key layout** (relative to bucket root):

```plain text
source-document-text/user/{ownerUserId}/document/{sourceDocumentId}/extraction/{extractionId}/
  plain.txt
  manifest.json
  blocks/block-000001.json
  chunks/chunk-000001.json
```

**Reading order for UBC:**

1. Fetch `manifest.json` from `extractedTextPackage.manifest` — confirms package version, block/chunk index, counts.
2. Fetch `plain.txt` from `extractedTextPackage.plainText` — primary text for heuristics/models.
3. Optionally list and fetch individual block/chunk objects under `blocksPrefix` and `chunksPrefix` for structured extraction or traceability.

Manifest schema version: `ednoda.extracted-source-document.v1`. Block files use `ednoda.extracted-source-document-block.v1`. Full field definitions: [source-document-text-package-contract.md](./source-document-text-package-contract.md).

**S3 access:** Production credential boundaries are TBD with task **10.6** (queue, cross-account role, presigned URLs, etc.). UBC code should accept bucket/key pointers and use whatever read mechanism Ednoda provisions. Do not assume inline bytes in the handoff payload.

### `original` — upload metadata

| Field | Description |
| --- | --- |
| `filename` | Original upload filename (not the S3 key) |
| `mimeType` | Declared MIME type |
| `fileExtension` | Extension including dot (e.g. `.pdf`, `.txt`) |

### `callback` — where UBC POSTs results

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `url` | URL | yes | `POST /api/source-documents/node-candidates/callback` on the Ednoda app |
| `signingHeader` | literal | yes | Must be `X-Ednoda-Signature` |
| `taskToken` | string or null | no | Step Functions task token when present; echo in output callback |

---

## Output / callback contract — what UBC returns

UBC POSTs JSON to `callback.url`. The body must validate as `sourceDocumentNodeCandidatesCallbackSchema` (output v1 plus optional idempotency fields).

### Top-level fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `version` | literal | yes | `source-document-candidate-extraction-result.v1` |
| `sourceDocumentId` | positive int | yes | Must match input |
| `extractionId` | positive int | yes | Must match input |
| `status` | enum | yes | `ready`, `partial`, or `failed` |
| `candidates` | array | yes | Zero or more candidate rows (see status rules) |
| `warnings` | string[] | no | Non-fatal quality notes |
| `error` | object | conditional | **Required** when `status` is `failed`; must be omitted for `ready` / `partial` |
| `taskToken` | string or null | no | Echo input `callback.taskToken` when present |

Optional idempotency fields (recommended when known): `workflowExecutionArn`, `workflowExecutionRowId`, `attemptNumber`, `occurredAtIso`.

### Status semantics

| Status | Meaning | `error` | `candidates` |
| --- | --- | --- | --- |
| `ready` | Extraction completed normally | Must be omitted | Zero or more — empty array is valid when nothing useful was found |
| `partial` | Completed with non-fatal degradation (truncation, skipped sections, low-confidence skips) | Must be omitted | Zero or more; document issues in `warnings` |
| `failed` | Extraction could not complete | **Required** (`code`, `message`; optional `details`) | Usually empty |

### Error object (when `status` is `failed`)

```json
{
  "code": "manifest_unreadable",
  "message": "Could not parse manifest.json from S3",
  "details": { "s3Key": "…/manifest.json" }
}
```

`details` is optional.

### Candidate row fields

Each candidate is a **metadata row** for teacher review — not a rewrite of the text package.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `candidateType` | enum | yes | See `candidateType` values below |
| `text` | string (min 1) | yes | Display text for review UI |
| `normalizedText` | string or null | no | Dedupe/matching key; Ednoda prefers this for upsert when set |
| `promptText` | string or null | no | Optional review hint (e.g. duplicated question wording). **Not** stored on `EducationNode`; conversion uses `text` only. |
| `answerText` | string or null | no | Optional review hint for paired Q&A material. **Not** used for conversion in MVP. |
| `sourceBlockId` | string or null | no | e.g. `block-000001` — links to S3 block file |
| `sourcePageNumber` | positive int or null | no | PDF page when known |
| `sourceSlideNumber` | positive int or null | no | PPTX slide when known |
| `confidence` | number 0–1 or null | no | Model confidence when applicable |
| `metadata` | object or null | no | UBC-owned JSON; Ednoda stores as `metadataJson` |

### `candidateType` enum values (MVP)

UBC should emit **only** these four strings. They align with Ednoda's atomic production node types (`vocab`, `expression`, `question`) plus an extractor fallback.

| Value | Typical use |
| --- | --- |
| `vocab` | Word / term entries (≤ 3 words) |
| `expression` | Phrases, collocations, frames, instructions, dialogue lines |
| `question` | Assessment / comprehension prompts |
| `unknown` | Use when classification is uncertain |

Put the teacher-facing string in **`text`**. Do not rely on `promptText` / `answerText` for conversion — those fields are optional review hints only.

**Invalid values:** Ednoda callbacks reject any `candidateType` outside the four values above. An earlier contract draft listed broader labels (`answer`, `grammar_pattern`, `phonics`, `dialogue`, `sentence_frame`, `activity_instruction`); UBC must not emit them — use `expression` or `unknown` instead. Those labels are original-PRD drift, not accepted runtime behavior.

`candidateType` is a **review label** aligned to atomic content, not a game template or QuestionVariant type. Teachers convert accepted candidates to `LessonNode` / `TextbookNode` via separate Ednoda logic.

**Traceability:** Prefer setting `sourceBlockId`, `sourcePageNumber`, or `sourceSlideNumber` when a candidate maps to a specific block in the S3 text package.

### Callback payload boundary

Do **not** embed in the callback:

- Full `plain.txt` body
- Block or chunk file contents
- Manifest JSON blobs
- Original file bytes
- Large base64 payloads

---

## Callback signing

**Route:** `POST {callback.url}` (typically `/api/source-documents/node-candidates/callback`)

**Authentication:** HMAC-SHA256 over the **raw JSON request body** (UTF-8 bytes), sent in the `X-Ednoda-Signature` header as a **lowercase hex** digest.

```
signature = HMAC-SHA256(SOURCE_DOCUMENT_CALLBACK_SECRET, rawBody).hex()
```

Rules:

- Serialize JSON once, sign those exact bytes, POST the same bytes. Do not re-serialize after signing.
- Shared secret: `SOURCE_DOCUMENT_CALLBACK_SECRET` (Ednoda provisions per environment).
- **Production fails closed:** missing secret or invalid signature returns `401 Unauthorized` (or `500` if Ednoda callback secret is misconfigured).

Reference implementation (Ednoda Python workers): `workers/source-documents/shared/callback_post.py` — `sign_callback_body`, `post_node_candidates_callback`.

---

## Idempotency and duplicate callbacks

Ednoda treats duplicate terminal callbacks as safe:

- **Replay:** Sending the same terminal callback again is acknowledged; already-converted candidates are **not** overwritten.
- **Upsert key** (same `sourceDocumentId` + `extractionId`):
  1. `candidateType + sourceBlockId + normalizedText` when both are set
  2. `candidateType + sourceBlockId + text` when `sourceBlockId` is set but `normalizedText` is not
  3. `candidateType + normalizedText` when no `sourceBlockId`
  4. `candidateType + text` as final fallback
- **Converted rows preserved:** If a candidate was already converted to an EducationNode, later callbacks skip updates for that row.
- **Deleted/missing documents:** Callback is acknowledged (`200`) without persisting candidates.

When `callback.taskToken` is present, Ednoda resolves the Step Functions task exactly once after signature validation. Stale duplicate callbacks do not re-send task completion.

---

## JSON examples

### Complete input example

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
      "key": "source-document-text/user/a1b2c3d4-e5f6-7890-abcd-ef1234567890/document/42/extraction/7/manifest.json"
    },
    "plainText": {
      "bucket": "ednoda-dev-source-document-text",
      "key": "source-document-text/user/a1b2c3d4-e5f6-7890-abcd-ef1234567890/document/42/extraction/7/plain.txt"
    },
    "chunksPrefix": {
      "bucket": "ednoda-dev-source-document-text",
      "prefix": "source-document-text/user/a1b2c3d4-e5f6-7890-abcd-ef1234567890/document/42/extraction/7/chunks/"
    },
    "blocksPrefix": {
      "bucket": "ednoda-dev-source-document-text",
      "prefix": "source-document-text/user/a1b2c3d4-e5f6-7890-abcd-ef1234567890/document/42/extraction/7/blocks/"
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
    "taskToken": "AQCEAAAAKgAAA-EXAMPLE-TASK-TOKEN-PLACEHOLDER"
  }
}
```

### Successful output — zero candidates

```json
{
  "version": "source-document-candidate-extraction-result.v1",
  "sourceDocumentId": 42,
  "extractionId": 7,
  "status": "ready",
  "candidates": [],
  "warnings": ["no_candidates_found"],
  "taskToken": "AQCEAAAAKgAAA-EXAMPLE-TASK-TOKEN-PLACEHOLDER"
}
```

### Successful output — multiple candidates

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
    },
    {
      "candidateType": "question",
      "text": "What is the past tense of \"go\"?",
      "normalizedText": "what is the past tense of go",
      "promptText": "What is the past tense of \"go\"?",
      "sourceBlockId": "block-000001",
      "confidence": 0.87
    },
    {
      "candidateType": "expression",
      "text": "Subject + past tense verb",
      "normalizedText": "subject past tense verb",
      "sourceBlockId": "block-000005",
      "confidence": 0.72
    }
  ],
  "taskToken": "AQCEAAAAKgAAA-EXAMPLE-TASK-TOKEN-PLACEHOLDER"
}
```

### Failed output

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
  "taskToken": "AQCEAAAAKgAAA-EXAMPLE-TASK-TOKEN-PLACEHOLDER"
}
```

---

## Minimal Python reference — S3 read + signed callback

Pseudo-code for UBC integration testing. Replace S3 client and secret sourcing with your deployment mechanism.

```python
import hashlib
import hmac
import json
import urllib.request

# --- 1. Receive handoff input (from queue, Lambda event, etc.) ---
handoff = {
    "version": "source-document-candidate-extraction.v1",
    "sourceDocumentId": 42,
    "extractionId": 7,
    "extractedTextPackage": {
        "manifest": {"bucket": "ednoda-dev-source-document-text", "key": "…/manifest.json"},
        "plainText": {"bucket": "ednoda-dev-source-document-text", "key": "…/plain.txt"},
        "blocksPrefix": {"bucket": "ednoda-dev-source-document-text", "prefix": "…/blocks/"},
    },
    "callback": {
        "url": "https://app.example.com/api/source-documents/node-candidates/callback",
        "signingHeader": "X-Ednoda-Signature",
        "taskToken": "AQCEAAAAKgAAA-EXAMPLE-TASK-TOKEN-PLACEHOLDER",
    },
}

# --- 2. Read text package from S3 (boto3 or agreed access) ---
# s3 = boto3.client("s3")
# manifest = json.loads(s3.get_object(Bucket=..., Key=...)["Body"].read())
# plain_text = s3.get_object(Bucket=..., Key=...)["Body"].read().decode("utf-8")

# --- 3. Run UBC extraction logic → build candidate rows ---
candidates = [
    {
        "candidateType": "vocab",
        "text": "example",
        "normalizedText": "example",
        "sourceBlockId": "block-000001",
    }
]

# --- 4. Build and sign callback body ---
callback_body = {
    "version": "source-document-candidate-extraction-result.v1",
    "sourceDocumentId": handoff["sourceDocumentId"],
    "extractionId": handoff["extractionId"],
    "status": "ready",
    "candidates": candidates,
    "taskToken": handoff["callback"].get("taskToken"),
}

secret = "REPLACE_WITH_SOURCE_DOCUMENT_CALLBACK_SECRET"  # from Ednoda env provisioning
raw_body = json.dumps(callback_body, separators=(",", ":"), sort_keys=True)
signature = hmac.new(
    secret.encode("utf-8"),
    raw_body.encode("utf-8"),
    hashlib.sha256,
).hexdigest()

request = urllib.request.Request(
    handoff["callback"]["url"],
    data=raw_body.encode("utf-8"),
    method="POST",
    headers={
        "Content-Type": "application/json",
        handoff["callback"]["signingHeader"]: signature,
    },
)

with urllib.request.urlopen(request, timeout=30) as response:
    assert response.status == 200
```

---

## What is explicitly out of scope for UBC

| Rule | Detail |
| --- | --- |
| No inline large payloads | Input and callbacks carry S3 pointers and candidate metadata only |
| No Postgres writes | UBC POSTs callback; Ednoda persists `SourceDocumentNodeCandidate` rows |
| No root-textbook targets | `textbookUnitId` must be set for textbook targets |
| No block Postgres table | Block bodies live in S3 only |
| No preview artifacts | Preview images are not part of this handoff |
| No production UBC dispatch wiring yet | Queue/SFN/cross-account invocation is Ednoda task **10.6** — deferred; local stubs are internal test harnesses only |

---

## Related Ednoda tasks

| Task | Status | Notes |
| --- | --- | --- |
| 9.11 text package handoff readiness | Complete | [ubc-text-package-handoff-readiness.md](./ubc-text-package-handoff-readiness.md) |
| 10.5 handoff payload builder | Complete | `lambda/source-documents/request-candidate-extraction.ts` |
| **10.6a UBC contract docs (this doc)** | Complete | Documentation only |
| 10.6b local adapter/stub harness | Complete for local/dev validation | Local TypeScript/Python harnesses exist; not UBC production |
| 10.6 UBC dispatch | **Deferred** | Real invocation when UBC is ready |

**Recommended next step for UBC:** Implement extraction against this contract and the text package doc. **Recommended next step for Ednoda:** keep local stubs aligned with this contract, then implement **10.6** when the production invocation mechanism is approved.
