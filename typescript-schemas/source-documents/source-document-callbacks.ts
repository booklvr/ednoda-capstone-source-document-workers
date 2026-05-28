/**
 * Signed worker callback payload schemas for Source Document pipeline routes.
 * Metadata and S3 pointers only — no large text, images, or block arrays.
 */

import { z } from 'zod'

import {
  sourceDocumentCandidateExtractionOutputCandidateSchema,
  sourceDocumentCandidateExtractionOutputStatusSchema,
  refineSourceDocumentCandidateExtractionStatus,
} from '@/schemas/source-documents/source-document-candidate-extraction'
import {
  nullablePositiveIntSchema,
  nullableSourceDocumentCallbackErrorSchema,
  nullableStringSchema,
  nonNegativeIntSchema,
  positiveIntSchema,
  sourceDocumentCallbackBaseSchema,
  sourceDocumentCallbackErrorSchema,
  sourceDocumentS3BucketSchema,
  sourceDocumentS3KeySchema,
} from '@/schemas/source-documents/source-document-contracts'
import {
  extractionStrategySchema,
  malwareScannerNameSchema,
  PreviewStrategy,
  previewStrategySchema,
  SourceDocumentExtractionStatus,
  SourceDocumentPreviewStatus,
  sourceDocumentExtractionStatusSchema,
  sourceDocumentMalwareScanStatusSchema,
  sourceDocumentPreviewStatusSchema,
  sourceDocumentWorkflowStatusSchema,
} from '@/schemas/source-documents/source-document-enums'

export const sourceDocumentPreviewPageCallbackSchema = z
  .object({
    pageNumber: positiveIntSchema,
    imageBucket: sourceDocumentS3BucketSchema.optional(),
    imageKey: sourceDocumentS3KeySchema,
    width: nullablePositiveIntSchema,
    height: nullablePositiveIntSchema,
  })
  .strict()

export type SourceDocumentPreviewPageCallback = z.infer<
  typeof sourceDocumentPreviewPageCallbackSchema
>

function refinePreviewCallback(
  value: {
    status: z.infer<typeof sourceDocumentPreviewStatusSchema>
    previewStrategy: z.infer<typeof previewStrategySchema>
    previewBucket?: string
    previewPrefix?: string
    pageCount?: number
    pages?: SourceDocumentPreviewPageCallback[]
    error: z.infer<typeof sourceDocumentCallbackErrorSchema> | null
  },
  ctx: z.RefinementCtx,
): void {
  const needsPreviewPointers =
    value.status === SourceDocumentPreviewStatus.ready ||
    value.status === SourceDocumentPreviewStatus.partial

  if (needsPreviewPointers && (!value.previewBucket || !value.previewPrefix)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message:
        'Preview callback with ready or partial status requires previewBucket and previewPrefix.',
      path: ['previewBucket'],
    })
  }

  if (value.status === SourceDocumentPreviewStatus.failed && !value.error) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Failed preview callback requires error.',
      path: ['error'],
    })
  }

  if (
    (value.status === SourceDocumentPreviewStatus.failed ||
      value.status === SourceDocumentPreviewStatus.unsupported) &&
    value.pages?.length
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message:
        'Failed or unsupported preview callbacks must not include page image rows.',
      path: ['pages'],
    })
  }

  if (
    value.previewStrategy === PreviewStrategy.plainText &&
    value.pages?.length
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Plain-text preview callbacks must not include page image rows.',
      path: ['pages'],
    })
  }

  const isPageImageTerminalCallback =
    value.previewStrategy === PreviewStrategy.pageImages && needsPreviewPointers

  if (isPageImageTerminalCallback) {
    if (!value.pages?.length) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message:
          'Page-image preview callbacks with ready or partial status require pages.',
        path: ['pages'],
      })
      return
    }

    if (
      value.pageCount !== undefined &&
      value.pageCount !== value.pages.length
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'pageCount must match the number of page image rows.',
        path: ['pageCount'],
      })
    }

    for (const page of value.pages) {
      if (!page.imageKey) {
        continue
      }
      if (!page.imageBucket && !value.previewBucket) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message:
            'Each page requires imageBucket or a top-level previewBucket to derive it.',
          path: ['pages'],
        })
        break
      }
    }
  }
}

/** Terminal statuses allowed on extraction callbacks. */
const EXTRACTION_CALLBACK_TERMINAL_STATUSES = [
  SourceDocumentExtractionStatus.ready,
  SourceDocumentExtractionStatus.partial,
  SourceDocumentExtractionStatus.failed,
  SourceDocumentExtractionStatus.ocrRequired,
] as const

/**
 * Zod super-refine for Alpha extraction callback shape.
 *
 * Enforces pointer rules: required for `ready` only at the app layer (server derives paths);
 * forbidden for `failed` and `ocr_required`; `error` required only for `failed`.
 */
function refineExtractionCallback(
  value: {
    status: z.infer<typeof sourceDocumentExtractionStatusSchema>
    textBucket?: string
    manifestKey?: string
    plainTextKey?: string
    error: z.infer<typeof sourceDocumentCallbackErrorSchema> | null
  },
  ctx: z.RefinementCtx,
): void {
  if (
    !EXTRACTION_CALLBACK_TERMINAL_STATUSES.includes(
      value.status as (typeof EXTRACTION_CALLBACK_TERMINAL_STATUSES)[number],
    )
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message:
        'Extraction callbacks may only use ready, partial, failed, or ocr_required.',
      path: ['status'],
    })
    return
  }

  if (
    (value.status === SourceDocumentExtractionStatus.ready ||
      value.status === SourceDocumentExtractionStatus.partial) &&
    value.error
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Ready or partial extraction callback must not include error.',
      path: ['error'],
    })
  }

  if (
    value.status === SourceDocumentExtractionStatus.failed ||
    value.status === SourceDocumentExtractionStatus.ocrRequired
  ) {
    if (value.textBucket || value.manifestKey || value.plainTextKey) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message:
          'Extraction callback must not include text package pointers for failed or ocr_required status.',
        path: ['textBucket'],
      })
    }
  }

  if (value.status === SourceDocumentExtractionStatus.failed && !value.error) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Failed extraction callback requires error.',
      path: ['error'],
    })
  }
}

export const sourceDocumentMalwareScanCallbackSchema =
  sourceDocumentCallbackBaseSchema
    .extend({
      status: sourceDocumentMalwareScanStatusSchema,
      scannerName: malwareScannerNameSchema,
      scannerVersion: nullableStringSchema,
      findingId: nullableStringSchema,
      findingSummary: nullableStringSchema,
    })
    .strict()

export type SourceDocumentMalwareScanCallback = z.infer<
  typeof sourceDocumentMalwareScanCallbackSchema
>

export const sourceDocumentPreviewCallbackSchema =
  sourceDocumentCallbackBaseSchema
    .extend({
      previewId: positiveIntSchema.optional(),
      status: sourceDocumentPreviewStatusSchema,
      previewStrategy: previewStrategySchema,
      pageCount: nonNegativeIntSchema.optional(),
      slideCount: nonNegativeIntSchema.optional(),
      previewBucket: sourceDocumentS3BucketSchema.optional(),
      previewPrefix: sourceDocumentS3KeySchema.optional(),
      pages: z.array(sourceDocumentPreviewPageCallbackSchema).optional(),
      warnings: z.array(z.string()).optional(),
      error: nullableSourceDocumentCallbackErrorSchema,
    })
    .strict()
    .superRefine(refinePreviewCallback)

export type SourceDocumentPreviewCallback = z.infer<
  typeof sourceDocumentPreviewCallbackSchema
>

/**
 * Text extraction worker callback — metadata and S3 pointers only (task 5.7).
 *
 * Alpha: `ready`, `failed`, or `ocr_required` only. `extractionId` is required.
 * Full text, blocks, and chunks stay in S3; never embed them in this payload.
 */
export const sourceDocumentExtractionCallbackSchema =
  sourceDocumentCallbackBaseSchema
    .extend({
      extractionId: positiveIntSchema,
      status: sourceDocumentExtractionStatusSchema,
      extractionStrategy: extractionStrategySchema,
      textBucket: sourceDocumentS3BucketSchema.optional(),
      manifestKey: sourceDocumentS3KeySchema.optional(),
      plainTextKey: sourceDocumentS3KeySchema.optional(),
      charCount: nonNegativeIntSchema.optional(),
      blockCount: nonNegativeIntSchema.optional(),
      chunkCount: nonNegativeIntSchema.optional(),
      pageCount: nonNegativeIntSchema.optional(),
      slideCount: nonNegativeIntSchema.optional(),
      tableCount: nonNegativeIntSchema.optional(),
      warnings: z.array(z.string()).optional(),
      error: nullableSourceDocumentCallbackErrorSchema,
    })
    .strict()
    .superRefine(refineExtractionCallback)

export type SourceDocumentExtractionCallback = z.infer<
  typeof sourceDocumentExtractionCallbackSchema
>

/** Node-candidate extraction callback: shared extraction output + callback idempotency fields. */
export const sourceDocumentNodeCandidatesCallbackSchema =
  sourceDocumentCallbackBaseSchema
    .extend({
      version: z.literal('source-document-candidate-extraction-result.v1'),
      extractionId: positiveIntSchema,
      status: sourceDocumentCandidateExtractionOutputStatusSchema,
      candidates: z.array(
        sourceDocumentCandidateExtractionOutputCandidateSchema,
      ),
      warnings: z.array(z.string()).optional(),
      error: nullableSourceDocumentCallbackErrorSchema,
    })
    .strict()
    .superRefine((value, ctx) => {
      refineSourceDocumentCandidateExtractionStatus(
        { status: value.status, error: value.error },
        ctx,
      )
    })

export type SourceDocumentNodeCandidatesCallback = z.infer<
  typeof sourceDocumentNodeCandidatesCallbackSchema
>

export const SourceDocumentWorkflowCallbackPhase = {
  started: 'started',
  finalized: 'finalized',
} as const

export const sourceDocumentWorkflowCallbackPhaseSchema = z.enum([
  SourceDocumentWorkflowCallbackPhase.started,
  SourceDocumentWorkflowCallbackPhase.finalized,
])

export const sourceDocumentWorkflowCallbackSchema =
  sourceDocumentCallbackBaseSchema
    .extend({
      phase: sourceDocumentWorkflowCallbackPhaseSchema,
      workflowStatus: sourceDocumentWorkflowStatusSchema,
      malwareScanStatus: sourceDocumentMalwareScanStatusSchema.optional(),
      previewStatus: z.string().min(1).optional(),
      extractionStatus: z.string().min(1).optional(),
      nodeCandidateStatus: z.string().min(1).optional(),
      blockedReason: nullableStringSchema,
    })
    .strict()

export type SourceDocumentWorkflowCallback = z.infer<
  typeof sourceDocumentWorkflowCallbackSchema
>
