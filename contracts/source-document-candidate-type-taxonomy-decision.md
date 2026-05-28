# Source Document Candidate Type Taxonomy Decision

**Task:** 10.6c — Candidate type taxonomy audit  
**Date:** 2026-05-20  
**Status:** Approved for cleanup (10.6d → 10.6e → 10.6f)

> **Amendment (2026-05-22):** Renamed candidate label `vocabulary` → `vocab` for 1:1 alignment with `EducationNode.nodeType`. UBC and workers must emit `vocab`, not `vocabulary`. Callbacks reject `vocabulary` (strict enum).

---

## 1. Executive decision

**Canonical Source Document candidate type set (Alpha + Full MVP):**

| `candidateType` | Role |
| --- | --- |
| `vocab` | Word / term entries (≤ 3 words after sanitization) |
| `expression` | Phrases, collocations, frames, instructions, dialogue lines, answers without Q/A pairing |
| `question` | Assessment / comprehension prompts |
| `unknown` | Extractor uncertainty — still reviewable; not convertible until re-labeled |

**Four values only.** No separate `answer`, `grammar_pattern`, `phonics`, `dialogue`, `sentence_frame`, or `activity_instruction` labels in the Source Document contract, Postgres ENUM, workers, or UBC handoff.

`candidateType` is a **review label** for extracted text, not Ednoda's full content taxonomy. It exists to help teachers sort candidates before one-click conversion — not to mirror every `EducationNode.nodeType` or game `QuestionVariant` shape.

---

## 2. Current bad state / smell

The feature shipped an **over-broad initial taxonomy** copied from an early PRD draft, then partially corrected in runtime without finishing the cleanup:

1. **Postgres ENUM drift** — Migration `20260519032039-create-source-document-node-candidates.js` defines **10** `candidate_type` values. App runtime defines **4** MVP values plus a separate `LegacyNodeCandidateType` bucket.
2. **Fake legacy compatibility layer** — `nodeCandidateTypeExtractionInputSchema` accepts 10 strings; `normalizeNodeCandidateTypeUtil` silently folds 6 legacy labels → `expression` (or `unknown` for unrecognized strings) before persist. This hides contract mistakes instead of rejecting them.
3. **Doc / prompt drift** — `prd.md`, `prompt-1.1`, and `prompt-2.10` still describe the broad 10-type set and composite Q/A / dialogue conversion paths that **were never implemented**.
4. **Partial UBC alignment** — `ubc-candidate-extraction-contract.md` and `source-document-candidate-extraction-contract.md` were updated in 10.6a to recommend 4 types, but ingress schemas and migration source still advertise legacy acceptance.
5. **Misleading PRD promise** — Original PRD listed `answer` as a first-class candidate type implying Q/A pairing, but conversion uses `candidateType + text` only via `findOrCreateNode` — no `composite_question_answer`, no `QuestionVariant` creation, no use of `promptText` / `answerText` at conversion time.

**Smell summary:** three competing truths (PRD, DB ENUM, runtime MVP) held together by normalization shims. UBC and browser smoke tests should not treat this as final until 10.6d–10.6f complete.

---

## 3. Existing Ednoda content types vs Source Document candidate labels

### `EducationNode.nodeType` (DB schema)

| `nodeType` | In teacher builder / `ATOMIC_NODE_TYPES`? | Source Document conversion today? |
| --- | --- | --- |
| `vocab` | Yes | Yes — via `vocab` candidate |
| `expression` | Yes | Yes — via `expression` and `unknown` candidates |
| `question` | Yes | Yes — via `question` candidate |
| `phonics` | No (exists in DB, not in `variantTypes.ts` NODE_TYPES) | **No** |
| `composite_question_answer` | No (commented out in builder; lesson-node schema supports it) | **No** |
| `composite_dialogue` | No (commented out in builder; lesson-node schema supports it) | **No** |

### Source Document → EducationNode mapping (implemented in `mapCandidateToEducationNodeInputUtil`)

```
vocab       → vocab       (≤ 3 words enforced)
expression  → expression
question    → question
unknown     → not convertible until re-labeled
```

**Not implemented (despite early prompt-2.10 draft):**

- `question` + `answerText` → `composite_question_answer`
- `dialogue` + structured metadata → `composite_dialogue`
- `phonics` → `phonics`
- Separate `answer` candidate type

Optional review fields `promptText` and `answerText` are stored on `SourceDocumentNodeCandidate` but **ignored at conversion**. They may help future review UI; they do not justify a separate `answer` candidate type in MVP.

---

## 4. Recommended Source Document candidate type set

**Emit, store, validate, and document only:**

```
vocab | expression | question | unknown
```

**Semantic guidance for extractors (UBC + stub):**

- **`vocab`** — Single terms or very short word entries (`term: definition`, `term - gloss`, ≤ 3 tokens after normalization).
- **`expression`** — Everything that is lesson content but not a standalone assessment prompt: collocations, sentence frames, grammar examples, dialogue lines, activity directions, model answers, phonics drill text.
- **`question`** — Text that functions as a prompt the teacher would turn into a `question` node (often contains `?` but heuristics should not require it).
- **`unknown`** — Extractor cannot classify confidently; teacher re-labels in review UI (future) or converts as expression.

**Dedupe key (10.7):** `sourceDocumentId + candidateType + normalizedText + sourceBlockId` — unchanged; works with 4-type set.

---

## 5. Values explicitly out of scope and why

| Label | Verdict | Reason |
| --- | --- | --- |
| `answer` | **Remove** | No Q/A pairing in conversion. Model answers are `expression` with content in `text`. `answerText` remains an optional review hint field, not a type. Legacy `answer` rows already normalize to `expression` with `answerText` folded into `text`. |
| `grammar_pattern` | **Remove** | Grammar patterns are expressions in Ednoda. No distinct node type or conversion branch. |
| `phonics` | **Remove** | `phonics` exists on `EducationNode` but is not product-supported in builder or `findOrCreateNode` Source Document path. Phonics drill text → `expression` until phonics is productized end-to-end. |
| `dialogue` | **Remove** | `composite_dialogue` is not exposed in teacher UI. Multi-line dialogue from documents should surface as one or more `expression` candidates (or future metadata on `expression`). Structured dialogue conversion requires composite node creation + line ordering — Phase 13+ at earliest. |
| `sentence_frame` | **Remove** | Sentence frames are expressions (`"I like ___"`, `"The ___ is ___"`). |
| `activity_instruction` | **Remove** | Worksheet/teacher-guide directions are expressions. Teachers rarely need a distinct filter bucket for Alpha. |

**Retained optional fields (not types):**

- `promptText`, `answerText` — review hints only; no conversion impact in MVP.
- `metadata` — worker-owned JSON; may carry dialogue line indices, frame slots, etc. for future UI without expanding the type enum.

---

## 6. UBC contract implication

**UBC must emit only:** `vocab`, `expression`, `question`, `unknown`.

Align with [ubc-candidate-extraction-contract.md](./ubc-candidate-extraction-contract.md) § `candidateType` (already drafted for 4 types in 10.6a).

**After 10.6d/10.6e:**

- Remove "legacy labels accepted on callbacks" language from UBC and external extraction docs.
- Callback Zod ingress should **reject** unknown `candidateType` strings (strict enum), not normalize them.
- Local stub (`workers/source-documents/candidate-extractor-stub/`) emits only `vocab`, `question`, `expression` — no change required except docs/tests.
- UBC local adapter (`ubc_local_adapter.py`) already uses the three productive types in dummy output — add `unknown` only in tests if needed.

**Classification rule of thumb for UBC:**

> When in doubt, prefer `expression` over inventing a legacy label. Use `unknown` only when the extractor genuinely cannot choose between vocab / expression / question.

---

## 7. Refactor inventory by file group

### Schemas / enums

| File | Current state | 10.6d action |
| --- | --- | --- |
| `src/schemas/source-documents/source-document-enums.ts` | `NodeCandidateType` (4) + `LegacyNodeCandidateType` (6) + `nodeCandidateTypeDbValues` (10) + `nodeCandidateTypeExtractionInputSchema` | Remove `LegacyNodeCandidateType`, `nodeCandidateTypeExtractionInputValues`, `nodeCandidateTypeExtractionInputSchema`; set `nodeCandidateTypeDbValues = NodeCandidateType` values |
| `src/schemas/source-documents/source-document-candidate-extraction.ts` | Uses `nodeCandidateTypeExtractionInputSchema` + normalize transform | Switch to `nodeCandidateTypeSchema`; remove normalize transform at schema boundary (or keep text coalescing only if still needed for `answerText` hints on `expression`) |
| `src/schemas/source-documents/source-document-candidate.ts` | Already uses `nodeCandidateTypeSchema` (4) | No enum change |
| `src/schemas/source-documents/source-document-callbacks.ts` | Delegates to extraction output schema | Verify after extraction schema change |

### Models / migrations

| File | Current state | Action |
| --- | --- | --- |
| `src/models/source-document-node-candidate.ts` | Sequelize ENUM via `nodeCandidateTypeDbValues` (10); Zod uses 4 | 10.6d: ENUM source → 4 values |
| `dist/migrations/20260519032039-create-source-document-node-candidates.js` | Postgres ENUM with 10 values | 10.6d: edit migration source to 4 values (do not run until 10.6f) |

### Callback ingress

| File | Current state | 10.6e action |
| --- | --- | --- |
| `src/utils/server/source-document/normalizeNodeCandidateTypeUtil.ts` | Legacy map + `normalizeExtractionOutputCandidateUtil` | Delete or reduce to text-field coalescing only; strict enum validation replaces type normalization |
| Node-candidates callback route / completion util | Uses extraction output schema | Verify strict reject on bad types |

### Normalization / conversion utils

| File | Current state | Action |
| --- | --- | --- |
| `src/utils/server/source-document/mapCandidateToEducationNodeInputUtil.ts` | 4-type switch — **correct** | No enum change; keep as-is |
| `src/utils/server/source-document/convertSourceDocumentCandidateUtil.ts` | Uses mapper — **correct** | No change |

### Workers / stubs

| File | Current state | Action |
| --- | --- | --- |
| `workers/source-documents/shared/contracts.py` | 3 constants only — **correct** | No change |
| `workers/source-documents/candidate-extractor-stub/heuristics.py` | Emits vocab/question/expression — **correct** | No change |
| `workers/source-documents/candidate-extractor-stub/ubc_local_adapter.py` | Emits vocab/question — **correct** | Optional: document that `answerText` on question stub is a hint only |

### Docs / prompts

| File | Stale content | 10.6e action |
| --- | --- | --- |
| `prd.md` | Lists 10 `candidateType` values in model shapes | Trim to 4; note optional `promptText`/`answerText` |
| `prompts/prompt-1.1-shared-enum-const-unions.md` | Lists 10 `NodeCandidateType` values | Update historical prompt or add deprecation note |
| `prompts/prompt-2.10-map-candidate-to-education-node-input-util.md` | Composite Q/A and dialogue mapping | Update to match implemented 4-type atomic mapping |
| `companion/model-shapes.md` | Already shows 4 + Legacy split | Remove legacy section after 10.6d |
| `companion/source-document-candidate-extraction-contract.md` | Already MVP 4 + legacy note | Remove legacy acceptance paragraph after 10.6e |
| `companion/ubc-candidate-extraction-contract.md` | Already MVP 4 + legacy note | Remove legacy acceptance paragraph after 10.6e |
| `companion/server-action-plan.md` | Generic `candidateType: z.string()` in places | Tighten to enum where applicable |

### Tests / fixtures

| File | Action |
| --- | --- |
| `tests/unit/utils/server/source-document/normalizeNodeCandidateTypeUtil.test.ts` | Delete or replace with strict-schema rejection tests (10.6e) |
| `tests/unit/utils/server/source-document/mapCandidateToEducationNodeInputUtil.test.ts` | Keep — already 4-type |
| `tests/factories/source-document-node-candidate.factory.ts` | Already uses `NodeCandidateType` — keep |
| `tests/integration/actions/source-document/serverFetchSourceDocumentCandidates.test.ts` | Already uses 4 types — keep |
| Worker tests under `workers/source-documents/candidate-extractor-stub/tests/` | Already 3 productive types — keep |

---

## 8. Migration reset strategy for non-live Source Document tables

Source Document tables are **pre-production / trusted-alpha only**. No public prod exposure yet. Safe to reset the candidate ENUM without data migration **if** no irreplaceable dev rows exist.

**Recommended sequence (10.6f — human approval required):**

1. Confirm no production/staging/demo rows depend on legacy `candidate_type` values (local dev: **unknown** — not queried in 10.6c per no-DB-access rule).
2. Roll back **only** Source Document migrations in dependency order, stopping at or including `20260519032039-create-source-document-node-candidates` — or drop/recreate the seven Source Document tables if simpler for local dev.
3. Apply corrected migration with `candidate_type` ENUM = `('vocab','expression','question','unknown')`.
4. Verify Sequelize model init, factory create, stub callback, and fetch action against 4-value ENUM.
5. **Do not** touch non–Source Document migrations or unrelated tables.

If legacy rows exist in dev, either:

- Accept one-time `UPDATE candidate_type = 'expression' WHERE candidate_type IN (...legacy...)` before ENUM shrink, or
- Truncate `source_document_node_candidates` (dev-only) before rollback.

---

## 9. Risks / open questions

| Risk | Mitigation |
| --- | --- |
| UBC built against 10-type PRD | 10.6a UBC contract already says 4 types; share this decision record before UBC integration |
| Hidden legacy rows in dev DB | 10.6f pre-check + truncate or UPDATE before ENUM shrink |
| Teachers want "Activity instructions" filter | Use `expression` + future metadata tag; revisit post-MVP if review UI needs a virtual filter |
| Q/A pairs from worksheets | Future: either two candidates (`question` + `expression`) or composite conversion in Phase 13+ — not a separate `answer` type |
| `unknown` vs `expression` for low confidence | Both convert to expression; `unknown` is for review UI sorting only |
| Prompt-2.10 composite mapping never built | Document as intentional deferral; do not resurrect without Phase 13 composite conversion |

**Open question:** Should callback ingress **reject** vs **coerce** unrecognized strings after legacy removal? **Recommendation:** reject (strict Zod enum) so UBC integration fails fast in dev.

---

## 10. Recommended next tasks

| Task | Scope |
| --- | --- |
| **10.6d** | Schema/model/migration-source refactor — remove `LegacyNodeCandidateType`, shrink ENUM definitions in code |
| **10.6e** | Feature-wide sweep — workers, callbacks, docs, prompts, tests; no surface advertises legacy labels |
| **10.6f** | With human approval: migration reset verification in local/dev |
| **13.2+** | If composite Q/A or dialogue conversion is productized, revisit whether new **candidate** labels are needed or whether metadata on `question`/`expression` pairs suffices |

**Do not proceed to 16.1 browser smoke or 17.1a deploy until 10.6d–10.6e at minimum are complete** — otherwise UBC and QA will validate against a contract that still accepts deprecated labels.

---

## Appendix A — All candidate type strings found (audit inventory)

### Canonical (keep)

- `vocab`
- `expression`
- `question`
- `unknown`

### Legacy (remove from contract)

- `answer`
- `grammar_pattern`
- `phonics`
- `dialogue`
- `sentence_frame`
- `activity_instruction`

### Code symbols (remove in 10.6d)

- `LegacyNodeCandidateType`
- `nodeCandidateTypeExtractionInputValues`
- `nodeCandidateTypeExtractionInputSchema`
- `nodeCandidateTypeDbValues` (as 10-member list — replace with 4-member list)
- `normalizeNodeCandidateTypeUtil` / legacy branches in `normalizeExtractionOutputCandidateUtil`

### Docs still listing legacy types

- `prd.md` (model shape sections)
- `prompts/prompt-1.1-shared-enum-const-unions.md`
- `prompts/prompt-2.10-map-candidate-to-education-node-input-util.md`
- `companion/source-document-candidate-extraction-contract.md` (legacy acceptance note — remove after sweep)
- `companion/ubc-candidate-extraction-contract.md` (legacy acceptance note — remove after sweep)
- `companion/model-shapes.md` (`LegacyNodeCandidateType` block — remove after 10.6d)

### Already aligned (no legacy emission)

- `workers/source-documents/shared/contracts.py`
- `workers/source-documents/candidate-extractor-stub/heuristics.py`
- `src/components/source-documents/SourceDocumentCandidateList.tsx`
- `src/utils/server/source-document/mapCandidateToEducationNodeInputUtil.ts`
