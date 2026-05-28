# UBC text package handoff readiness (task 9.11)

Verified **2026-05-20** on branch `feature/source-documents`.

## Purpose

Confirm that Ednoda's Alpha text extraction pipeline produces a **predictable, documented, testable, candidate-type-free S3 text package** sufficient for a future UBC (external Python team) candidate extraction consumer. This task verifies Ednoda's side of the handoff only — **no production UBC dispatch is implemented or enabled**.

**Boundary index:** [source-document-data-contract-boundaries.md](./source-document-data-contract-boundaries.md)

## Ownership boundary

| Owner | Responsibilities |
| --- | --- |
| **Ednoda** | Document upload, malware gate, preview generation, text extraction when possible, deterministic S3 key layout, writing the text package (`plain.txt`, blocks, chunks, `manifest.json`), signed extraction callback, Postgres pointers/counts only |
| **UBC (external Python team)** | Reading the S3 text package, running candidate extraction heuristics/models, POSTing signed node-candidates callback (future — task **10.6**) |

Alpha uses an Ednoda-owned **deterministic candidate stub** (tasks **10.1**–**10.2**) for UI/testing. That stub is separate from UBC and is not part of this handoff verification.

## S3 text package artifacts (`ready` only)

For extraction status `ready`, the `text-extractor` worker writes:

```plain text
source-document-text/user/{ownerUserId}/document/{sourceDocumentId}/extraction/{extractionId}/
  plain.txt
  blocks/block-000001.json
  chunks/chunk-000001.json
  manifest.json          ← written last (completion marker)
```

**Write ordering:** `plain.txt` → block files → chunk files → `manifest.json` last. The extraction callback is sent only after a successful package write (handler posts callback after `process_text_extraction` returns).

**Key determinism:** Keys derive from `ownerUserId`, `sourceDocumentId`, and `extractionId` only — never from untrusted filenames.

| Component | Location |
| --- | --- |
| Worker key builder | `workers/source-documents/shared/keys.py` — `build_extraction_text_package_keys` |
| Server key builder | `src/utils/server/source-document/buildSourceDocumentExtractionTextPackageKeysUtil.ts` |
| Package writer | `workers/source-documents/text-extractor/package_writer.py` — `write_text_package` |

## Manifest version and schema

| Literal | Usage |
| --- | --- |
| `ednoda.extracted-source-document.v1` | Root `version` in `manifest.json` |
| `ednoda.extracted-source-document-block.v1` | Each `blocks/block-*.json` file |

**Canonical Zod schemas:** `src/schemas/source-documents/source-document-text-package.ts`

- `extractedSourceDocumentManifestV1Schema`
- `extractedSourceDocumentBlockV1Schema`

**Full contract doc:** [source-document-text-package-contract.md](./source-document-text-package-contract.md)

## Terminal status behavior

| Status | S3 text package | Callback / Postgres pointers |
| --- | --- | --- |
| `ready` | Full package written | Server-derived `textBucket`, `manifestKey`, `plainTextKey`; worker may echo but must match |
| `ocr_required` | **None** — no S3 writes | **None** — status, strategy, `pageCount`, `warnings` only |
| `failed` | **None** | **None** — `error` required |

Worker: `handler.py` returns `build_ocr_required_result` before any S3 package write when PDF coverage is insufficient. Failed paths never call `write_text_package`.

Server: `resolveSourceDocumentExtractionCallbackPointers` in `validateSourceDocumentExtractionCallbackPathsUtil.ts` rejects pointer fields for `ocr_required` and `failed`, and returns null pointers for persistence.

`completeSourceDocumentExtractionCallbackUtil` does **not** read S3 — it persists pointers, counts, warnings, and errors only.

## Postgres boundary

`SourceDocumentExtraction` stores aggregate counts and S3 pointer columns only. **No `SourceDocumentExtractedBlock` table exists or is planned.** Block/chunk bodies live in S3 only.

## UBC dispatch — explicitly deferred

Task **10.6** remains **unchecked and blocked** until UBC is ready and a production invocation mechanism is documented and approved.

Current behavior:

- `lambda/source-documents/request-candidate-extraction.ts` builds a compact `SourceDocumentCandidateExtractionInputV1` payload. In `dev`, `staging`, and `demo`, it may post a local TypeScript stub callback for internal UI/testing when callback signing is configured; otherwise it returns `dispatchStatus: 'not_sent'` with `dispatch.mechanism: 'deferred'`. **No production queue, cross-account invocation, or external UBC worker call exists yet.**
- Step Functions `EvaluateCandidateHandoff` invokes `request-candidate-extraction` only when extraction is `ready` with text package pointers present; it does not dispatch to UBC.
- Prompt `prompt-10.6-candidate-extraction-dispatch-mechanism.md` is **superseded / do not run**.

**Future handoff contract (not active):** [source-document-candidate-extraction-contract.md](./source-document-candidate-extraction-contract.md)

## Verification evidence

| Check | Result |
| --- | --- |
| `pnpm run typecheck` | Pass |
| `buildSourceDocumentExtractionTextPackageKeysUtil.test.ts` | 3 tests pass |
| `completeSourceDocumentExtractionCallbackUtil.test.ts` | 5 tests pass (ready pointers, ocr_required null pointers, failed, stale, mismatch rejection) |
| `text-extractor/tests/test_text_extractor.py` | 11/12 pass; 1 test skipped (`botocore` not installed locally — do not install in this task) |
| Manifest-last write order | Covered by `test_handler_processes_txt_and_writes_manifest_last` |
| No production UBC/external dispatch | Confirmed in `request-candidate-extraction.ts` and SFN state machine |

## Related tasks

| Task | Status |
| --- | --- |
| 9.1–9.4 Alpha text package | Complete |
| 9.10 text-extractor SFN bridge | Complete |
| **9.11 handoff readiness (this doc)** | Complete |
| 10.5 handoff payload builder | Complete |
| 10.6 UBC dispatch mechanism | **Deferred** |

## Recommended next task

When UBC is ready: unblock and implement **10.6** (candidate extraction dispatch mechanism) using the v1 handoff payload from **10.5**. Until then, continue Alpha UI work (**Phase 11–13**) using the deterministic candidate stub.
