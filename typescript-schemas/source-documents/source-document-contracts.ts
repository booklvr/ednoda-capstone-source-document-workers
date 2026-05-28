/**
 * Shared Source Document contract primitives reused across schemas.
 * IDs, environments, S3 pointers, callback base fields, and MIME allowlists.
 */

import { z } from 'zod'

export const positiveIntSchema = z.number().int().positive()
export const nonNegativeIntSchema = z.number().int().nonnegative()

export const sourceDocumentS3BucketSchema = z.string().min(1).max(255)
export const sourceDocumentS3KeySchema = z.string().min(1).max(2048)

export const sourceDocumentIdSchema = positiveIntSchema

export const sourceDocumentEnvironmentSchema = z.enum([
  'dev',
  'staging',
  'demo',
  'prod',
])

export const isoDateTimeSchema = z.string().datetime()
export const nullableIsoDateTimeSchema = z.string().datetime().nullable()

export const nullableStringSchema = z
  .string()
  .nullish()
  .transform((value) => value ?? null)

export const nullableTaskTokenSchema = z
  .string()
  .nullish()
  .transform((value) => value ?? null)

export const nullableWorkflowExecutionArnSchema = z
  .string()
  .min(1)
  .nullish()
  .transform((value) => value ?? null)

export const nullablePositiveIntSchema = positiveIntSchema
  .nullish()
  .transform((value) => value ?? null)

export const sourceDocumentS3PointerSchema = z
  .object({
    bucket: sourceDocumentS3BucketSchema,
    key: sourceDocumentS3KeySchema,
  })
  .strict()

export const sourceDocumentS3PrefixPointerSchema = z
  .object({
    bucket: sourceDocumentS3BucketSchema,
    prefix: sourceDocumentS3KeySchema,
  })
  .strict()

/** Structured worker error summary; avoid large nested detail blobs. */
export const sourceDocumentCallbackErrorSchema = z
  .object({
    code: z.string().min(1),
    message: z.string().min(1),
    details: z.record(z.string(), z.unknown()).optional(),
  })
  .strict()

export type SourceDocumentCallbackError = z.infer<
  typeof sourceDocumentCallbackErrorSchema
>

export const nullableSourceDocumentCallbackErrorSchema =
  sourceDocumentCallbackErrorSchema
    .nullish()
    .transform((value) => value ?? null)

/**
 * Common idempotency fields for signed Ednoda callback routes.
 * `workflowExecutionArn` is the Step Functions execution ARN when known.
 * `workflowExecutionRowId` is the Postgres `source_document_workflow_executions.id` FK when known.
 */
export const sourceDocumentByIdInputSchema = z
  .object({
    sourceDocumentId: sourceDocumentIdSchema,
  })
  .strict()

export type SourceDocumentByIdInput = z.infer<
  typeof sourceDocumentByIdInputSchema
>

/** Original uploaded file pointer in Step Functions workflow input. */
export const sourceDocumentWorkflowOriginalSchema = z
  .object({
    bucket: sourceDocumentS3BucketSchema,
    key: sourceDocumentS3KeySchema,
    mimeType: z.string().min(1).max(255),
    fileExtension: z.string().min(1).max(32),
    fileSizeBytes: nonNegativeIntSchema,
    eTag: z.string().min(1).optional(),
  })
  .strict()

export const sourceDocumentCallbackBaseSchema = z
  .object({
    sourceDocumentId: sourceDocumentIdSchema,
    workflowExecutionArn: nullableWorkflowExecutionArnSchema.optional(),
    workflowExecutionRowId: nullablePositiveIntSchema.optional(),
    attemptNumber: positiveIntSchema.optional(),
    taskToken: nullableTaskTokenSchema.optional(),
    occurredAtIso: isoDateTimeSchema.optional(),
  })
  .strict()

export const SourceDocumentSupportedMimeType = {
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  csv: 'text/csv',
  plainText: 'text/plain',
} as const

export const sourceDocumentSupportedMimeTypeSchema = z.enum([
  SourceDocumentSupportedMimeType.pdf,
  SourceDocumentSupportedMimeType.docx,
  SourceDocumentSupportedMimeType.pptx,
  SourceDocumentSupportedMimeType.csv,
  SourceDocumentSupportedMimeType.plainText,
])

export type SourceDocumentSupportedMimeType = z.infer<
  typeof sourceDocumentSupportedMimeTypeSchema
>

/** Lowercase extensions without a leading dot. */
export const SOURCE_DOCUMENT_SUPPORTED_FILE_EXTENSIONS = [
  'pdf',
  'docx',
  'pptx',
  'csv',
  'txt',
] as const

export type SourceDocumentSupportedFileExtension =
  (typeof SOURCE_DOCUMENT_SUPPORTED_FILE_EXTENSIONS)[number]

const mimeTypeToExtensions: Record<
  SourceDocumentSupportedMimeType,
  readonly SourceDocumentSupportedFileExtension[]
> = {
  [SourceDocumentSupportedMimeType.pdf]: ['pdf'],
  [SourceDocumentSupportedMimeType.docx]: ['docx'],
  [SourceDocumentSupportedMimeType.pptx]: ['pptx'],
  [SourceDocumentSupportedMimeType.csv]: ['csv'],
  [SourceDocumentSupportedMimeType.plainText]: ['txt'],
}

export function parseSourceDocumentFileExtension(
  filename: string,
): SourceDocumentSupportedFileExtension | null {
  const lastDotIndex = filename.lastIndexOf('.')
  if (lastDotIndex <= 0 || lastDotIndex === filename.length - 1) {
    return null
  }

  const extension = filename
    .slice(lastDotIndex + 1)
    .toLowerCase() as SourceDocumentSupportedFileExtension

  return SOURCE_DOCUMENT_SUPPORTED_FILE_EXTENSIONS.includes(extension)
    ? extension
    : null
}

export function sourceDocumentMimeTypeMatchesExtension(params: {
  mimeType: SourceDocumentSupportedMimeType
  fileExtension: SourceDocumentSupportedFileExtension
}): boolean {
  return mimeTypeToExtensions[params.mimeType].includes(params.fileExtension)
}
