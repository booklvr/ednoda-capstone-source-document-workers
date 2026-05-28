/**
 * Lambda-only Step Functions task input schemas.
 * Shared cross-boundary contracts live in `src/schemas/source-documents/*`.
 */

import { z } from 'zod'

import { sourceDocumentTargetSchema } from '../../../src/schemas/source-documents/source-document'
import {
  nonNegativeIntSchema,
  positiveIntSchema,
  sourceDocumentEnvironmentSchema,
  sourceDocumentIdSchema,
  sourceDocumentS3BucketSchema,
  sourceDocumentS3KeySchema,
  sourceDocumentWorkflowOriginalSchema,
} from '../../../src/schemas/source-documents/source-document-contracts'

export const workflowStepContextSchema = z
  .object({
    sourceDocumentId: sourceDocumentIdSchema,
    workflowExecutionArn: z.string().min(1).optional(),
    workflowExecutionRowId: positiveIntSchema.optional(),
    attemptNumber: positiveIntSchema.optional(),
    taskToken: z.string().min(1).nullable().optional(),
  })
  .strict()

export const updateStatusInputSchema = workflowStepContextSchema
  .extend({
    branch: z.enum([
      'workflow',
      'malware_scan',
      'preview',
      'extraction',
      'node_candidate',
    ]),
    status: z.string().min(1),
    errorCode: z.string().nullable().optional(),
    errorMessage: z.string().nullable().optional(),
  })
  .strict()

export const finalizeWorkflowInputSchema = workflowStepContextSchema
  .extend({
    previewStatus: z.string().min(1).optional(),
    extractionStatus: z.string().min(1).optional(),
    nodeCandidateStatus: z.string().min(1).optional(),
    malwareScanStatus: z.string().min(1).optional(),
    blockedReason: z.string().nullable().optional(),
  })
  .strict()

export const candidateHandoffInputSchema = workflowStepContextSchema
  .extend({
    environment: sourceDocumentEnvironmentSchema,
    target: sourceDocumentTargetSchema,
    original: sourceDocumentWorkflowOriginalSchema,
    extractionId: positiveIntSchema,
    textBucket: sourceDocumentS3BucketSchema,
    manifestKey: sourceDocumentS3KeySchema,
    plainTextKey: sourceDocumentS3KeySchema,
    charCount: nonNegativeIntSchema.optional(),
    blockCount: nonNegativeIntSchema.optional(),
    chunkCount: nonNegativeIntSchema.optional(),
  })
  .strict()

export type CandidateHandoffInput = z.infer<typeof candidateHandoffInputSchema>
