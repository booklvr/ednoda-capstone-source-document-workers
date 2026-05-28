# Worker limit environment variables (task 0.8)

Defined **2026-05-18** on branch `feature/source-documents`. Documentation only — no worker enforcement in this task.

## Purpose

These limits cap **how much work a Source Document worker processes** after a file has already passed app upload validation. They are **not** general Next.js app configuration and are **not** upload size checks.

When a limit is hit during Full MVP worker implementation (master plan **8.8**, **8.9**, **9.6**, **9.7**), workers should truncate or stop as specified and set **`previewStatus = partial`** or **`extractionStatus = partial`** (or failed where appropriate), with reasons recorded in attempt `warningsJson`.

## Separate from upload file size

| Variable | Where | Role |
| --- | --- | --- |
| `SOURCE_DOCUMENT_MAX_FILE_SIZE_BYTES=52428800` | **Ednoda app** (`.env.local`, server actions) | Rejects uploads over 50 MB at presign/create time (task **0.4**, Phase **6**). |
| `MAX_DOCUMENT_SIZE_BYTES=52428800` | **Workers** (optional mirror) | Worker may refuse to open objects larger than the app cap; same 50 MB product limit, not a preview/extraction truncation limit. |

The six variables below are **worker processing limits**, not upload validation.

## Ownership and configuration surface

| Surface | Include worker limits? |
| --- | --- |
| Next.js `.env` / `.env.local` | **No** (unless you run a worker process locally and choose to mirror CDK env for convenience). |
| `src/lib/config.ts`, `src/utils/env.ts` | **No** — no central env registry; do not add these in task 0.8. |
| CDK Lambda environment (Phase **3**+) | **Yes** — canonical deploy-time source per environment. |
| AWS Secrets Manager / platform secrets | **No** — numeric limits are not secrets. |
| Local worker dev config (future) | **Yes** — same names when running preview/extraction Lambdas locally. |

Exact numeric values were **TBD** until Full MVP worker implementation (**2026-05-22**). Chosen defaults are documented below and wired in CDK container worker env for preview/extraction Lambdas.

**Chosen Full MVP defaults (2026-05-22):** `MAX_PREVIEW_PAGES=50`, `MAX_TABLE_ROWS_FOR_PREVIEW=200`, `MAX_EXTRACTION_CHARS=500000`, `MAX_BLOCKS=5000`, `MAX_CHUNKS=5000`, `MAX_PROCESSING_SECONDS=240`.

**Alpha (`[Alpha]`):** PDF/TXT stub workers may use internal hardcoded placeholders; they do not require finalized limits in app env. **Full MVP (`[Full]`):** limits and partial-result behavior must be defined and wired before full preview/extraction workers ship.

## Variables

| Env var | Worker(s) | Limits | On exceed (Full MVP) | Master plan |
| --- | --- | --- | --- | --- |
| `MAX_PREVIEW_PAGES` | Preview (PDF page images) | Max WebP pages written per preview attempt | Truncate pages; `previewStatus = partial`; warning in preview attempt | **8.8** |
| `MAX_TABLE_ROWS_FOR_PREVIEW` | Preview (CSV) | Max data rows in CSV preview JSON | Truncate rows; `previewStatus = partial`; warning in preview attempt | **8.9** |
| `MAX_EXTRACTION_CHARS` | Extraction | Max total extracted character count in text package | Truncate text; `extractionStatus = partial`; `warningsJson` | **9.6** |
| `MAX_BLOCKS` | Extraction | Max blocks in S3 `manifest.json` / block files | Truncate blocks; `extractionStatus = partial`; `warningsJson` | **9.6** |
| `MAX_CHUNKS` | Extraction | Max chunks in extracted text package | Truncate chunks; `extractionStatus = partial`; `warningsJson` | **9.6** |
| `MAX_PROCESSING_SECONDS` | Preview, extraction | Wall-clock budget for one worker invocation | Failed or partial with timeout warning (per worker design) | **9.7** |

### Example CDK / worker block (placeholders)

```env
# Worker Lambdas only — Full MVP defaults (2026-05-22)
MAX_PREVIEW_PAGES=50
MAX_TABLE_ROWS_FOR_PREVIEW=200
MAX_EXTRACTION_CHARS=500000
MAX_BLOCKS=5000
MAX_CHUNKS=5000
MAX_PROCESSING_SECONDS=240

# Upload cap mirror (optional on workers; same 50 MB as app)
MAX_DOCUMENT_SIZE_BYTES=52428800
```

## Value selection (before Phase 8/9)

Defaults committed **2026-05-22** for Full MVP (see example block above). Prefer conservative caps aligned with Lambda timeout/memory, S3 artifact size, and UI polling expectations. Document per-environment overrides in [aws-infrastructure-plan.md](./aws-infrastructure-plan.md) if they differ.

## Related docs

- [master-plan.md](../master-plan.md) — tasks **0.8**, **8.8**, **8.9**, **9.6**, **9.7**
- [aws-infrastructure-plan.md](./aws-infrastructure-plan.md) — worker env var list for CDK
- [prd.md](../prd.md) — partial `previewStatus` / `extractionStatus` behavior
- [docs/guides/setup-development-environment.md](../../../../docs/guides/setup-development-environment.md) — app vs worker env split
