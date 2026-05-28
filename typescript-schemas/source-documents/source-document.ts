/**
 * Shared Source Document target-context and summary output schemas.
 * Used by server actions, stores, and UI at API boundaries.
 */

import { z } from 'zod'

import {
  nullableIsoDateTimeSchema,
  isoDateTimeSchema,
  positiveIntSchema,
  sourceDocumentIdSchema,
} from '@/schemas/source-documents/source-document-contracts'
import {
  SourceDocumentTargetType,
  sourceDocumentExtractionStatusSchema,
  sourceDocumentKindSchema,
  sourceDocumentMalwareScanStatusSchema,
  sourceDocumentNodeCandidateStatusSchema,
  sourceDocumentPreviewStatusSchema,
  sourceDocumentTargetTypeSchema,
  sourceDocumentUploadStatusSchema,
  sourceDocumentWorkflowStatusSchema,
} from '@/schemas/source-documents/source-document-enums'

const sourceDocumentLessonTargetSchema = z
  .object({
    targetType: z.literal(SourceDocumentTargetType.lesson),
    lessonId: positiveIntSchema,
    defaultQuestionListId: positiveIntSchema.optional(),
  })
  .strict()

const sourceDocumentTextbookUnitTargetSchema = z
  .object({
    targetType: z.literal(SourceDocumentTargetType.textbookUnit),
    textbookId: positiveIntSchema,
    textbookUnitId: positiveIntSchema,
  })
  .strict()

/** Canonical discriminated target for uploads, workflow input, and candidate extraction. */
export const sourceDocumentTargetSchema = z.discriminatedUnion('targetType', [
  sourceDocumentLessonTargetSchema,
  sourceDocumentTextbookUnitTargetSchema,
])

export type SourceDocumentTarget = z.infer<typeof sourceDocumentTargetSchema>

/** Denormalized target columns on a SourceDocument row (summary/list output). */
export const sourceDocumentSummarySchema = z
  .object({
    id: sourceDocumentIdSchema,
    ownerUserId: z.string().uuid(),
    targetType: sourceDocumentTargetTypeSchema,
    lessonId: positiveIntSchema.nullable(),
    textbookId: positiveIntSchema.nullable(),
    textbookUnitId: positiveIntSchema.nullable(),
    defaultQuestionListId: positiveIntSchema.nullable(),
    originalFilename: z.string(),
    safeFilename: z.string(),
    originalMimeType: z.string(),
    fileExtension: z.string(),
    fileSizeBytes: z.number().int().nonnegative(),
    documentKind: sourceDocumentKindSchema,
    uploadStatus: sourceDocumentUploadStatusSchema,
    malwareScanStatus: sourceDocumentMalwareScanStatusSchema,
    workflowStatus: sourceDocumentWorkflowStatusSchema,
    previewStatus: sourceDocumentPreviewStatusSchema,
    extractionStatus: sourceDocumentExtractionStatusSchema,
    nodeCandidateStatus: sourceDocumentNodeCandidateStatusSchema,
    lastErrorCode: z.string().nullable(),
    lastErrorMessage: z.string().nullable(),
    uploadedAt: nullableIsoDateTimeSchema,
    malwareScannedAt: nullableIsoDateTimeSchema,
    previewReadyAt: nullableIsoDateTimeSchema,
    extractionReadyAt: nullableIsoDateTimeSchema,
    nodeCandidatesReadyAt: nullableIsoDateTimeSchema,
    deletionRequestedAt: nullableIsoDateTimeSchema,
    createdAt: isoDateTimeSchema,
    updatedAt: isoDateTimeSchema,
  })
  .strict()

export type SourceDocumentSummary = z.infer<typeof sourceDocumentSummarySchema>

/** Stable cache key for list/upload state scoped to a lesson or textbook unit. */
export function buildSourceDocumentTargetKey(
  target: SourceDocumentTarget,
): string {
  if (target.targetType === SourceDocumentTargetType.lesson) {
    return `${SourceDocumentTargetType.lesson}:${target.lessonId}`
  }

  return `${SourceDocumentTargetType.textbookUnit}:${target.textbookId}:${target.textbookUnitId}`
}

