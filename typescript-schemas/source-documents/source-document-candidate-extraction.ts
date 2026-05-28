/**
 * Candidate extraction handoff contract (input/output v1).
 *
 * Input: S3 text package pointers only (from completed text extraction). Output: candidate
 * rows with candidateType — the first pipeline step that assigns vocab / expression /
 * question / unknown. Text extraction must never emit those labels. Ednoda owns validation,
 * callbacks, and persistence; UBC/stub owns extraction heuristics.
 */

import { z } from 'zod'

import { sourceDocumentTargetSchema } from '@/schemas/source-documents/source-document'
import {
  nullableSourceDocumentCallbackErrorSchema,
  nullableStringSchema,
  nullableTaskTokenSchema,
  positiveIntSchema,
  sourceDocumentEnvironmentSchema,
  sourceDocumentIdSchema,
  sourceDocumentS3PointerSchema,
  sourceDocumentS3PrefixPointerSchema,
  type SourceDocumentCallbackError,
} from '@/schemas/source-documents/source-document-contracts'
import { nodeCandidateTypeSchema } from '@/schemas/source-documents/source-document-enums'

const sourceDocumentCandidateExtractionExtractedTextPackageSchema = z
  .object({
    manifest: sourceDocumentS3PointerSchema,
    plainText: sourceDocumentS3PointerSchema,
    chunksPrefix: sourceDocumentS3PrefixPointerSchema.optional(),
    blocksPrefix: sourceDocumentS3PrefixPointerSchema.optional(),
  })
  .strict()

const sourceDocumentCandidateExtractionOriginalSchema = z
  .object({
    filename: z.string().min(1),
    mimeType: z.string().min(1),
    fileExtension: z.string().min(1),
  })
  .strict()

const sourceDocumentCandidateExtractionCallbackSchema = z
  .object({
    url: z.string().url(),
    signingHeader: z.literal('X-Ednoda-Signature'),
    taskToken: z.string().min(1).nullish(),
  })
  .strict()
  .transform((value) => ({
    url: value.url,
    signingHeader: value.signingHeader,
    taskToken: value.taskToken ?? null,
  }))

export const sourceDocumentCandidateExtractionInputV1Schema = z
  .object({
    version: z.literal('source-document-candidate-extraction.v1'),
    environment: sourceDocumentEnvironmentSchema,
    sourceDocumentId: sourceDocumentIdSchema,
    extractionId: positiveIntSchema,
    target: sourceDocumentTargetSchema,
    extractedTextPackage:
      sourceDocumentCandidateExtractionExtractedTextPackageSchema,
    original: sourceDocumentCandidateExtractionOriginalSchema,
    callback: sourceDocumentCandidateExtractionCallbackSchema,
  })
  .strict()

export type SourceDocumentCandidateExtractionInputV1 = z.infer<
  typeof sourceDocumentCandidateExtractionInputV1Schema
>

export const sourceDocumentCandidateExtractionOutputStatusSchema = z.enum([
  'ready',
  'partial',
  'failed',
])

export type SourceDocumentCandidateExtractionOutputStatus = z.infer<
  typeof sourceDocumentCandidateExtractionOutputStatusSchema
>

export const sourceDocumentCandidateExtractionOutputCandidateSchema = z
  .object({
    candidateType: nodeCandidateTypeSchema,
    text: z.string().min(1),
    normalizedText: nullableStringSchema.optional(),
    promptText: nullableStringSchema.optional(),
    answerText: nullableStringSchema.optional(),
    sourceBlockId: z.string().min(1).nullish(),
    sourcePageNumber: positiveIntSchema.nullish(),
    sourceSlideNumber: positiveIntSchema.nullish(),
    confidence: z.number().min(0).max(1).nullish(),
    metadata: z.record(z.unknown()).nullish(),
  })
  .strict()
  .transform((value) => ({
    candidateType: value.candidateType,
    text: value.text,
    normalizedText: value.normalizedText ?? null,
    promptText: value.promptText ?? null,
    answerText: value.answerText ?? null,
    sourceBlockId: value.sourceBlockId ?? null,
    sourcePageNumber: value.sourcePageNumber ?? null,
    sourceSlideNumber: value.sourceSlideNumber ?? null,
    confidence: value.confidence ?? null,
    metadata: value.metadata ?? null,
  }))

export type SourceDocumentCandidateExtractionOutputCandidate = z.infer<
  typeof sourceDocumentCandidateExtractionOutputCandidateSchema
>

export function refineSourceDocumentCandidateExtractionStatus(
  value: {
    status: SourceDocumentCandidateExtractionOutputStatus
    error: SourceDocumentCallbackError | null
  },
  ctx: z.RefinementCtx,
): void {
  if ((value.status === 'ready' || value.status === 'partial') && value.error) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message:
        'Candidate extraction result with ready/partial status must not include error.',
      path: ['error'],
    })
  }

  if (value.status === 'failed' && !value.error) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Failed candidate extraction result requires error.',
      path: ['error'],
    })
  }
}

export const sourceDocumentCandidateExtractionOutputV1Schema = z
  .object({
    version: z.literal('source-document-candidate-extraction-result.v1'),
    sourceDocumentId: sourceDocumentIdSchema,
    extractionId: positiveIntSchema,
    status: sourceDocumentCandidateExtractionOutputStatusSchema,
    candidates: z.array(sourceDocumentCandidateExtractionOutputCandidateSchema),
    warnings: z.array(z.string()).optional(),
    error: nullableSourceDocumentCallbackErrorSchema,
    taskToken: nullableTaskTokenSchema.optional(),
  })
  .strict()
  .superRefine(refineSourceDocumentCandidateExtractionStatus)

export type SourceDocumentCandidateExtractionOutputV1 = z.infer<
  typeof sourceDocumentCandidateExtractionOutputV1Schema
>
