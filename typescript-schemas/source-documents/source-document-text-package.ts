/**
 * S3 text package and Step Functions workflow input contracts for Source Documents.
 *
 * Text extraction produces candidate-type-free packages only: manifest.json, plain.txt,
 * blocks/*.json, chunks/*.json, plus extraction status/counts/warnings. No candidateType
 * or NodeCandidateType values appear here — semantic classification happens in candidate
 * extraction (UBC/stub). See companion/source-document-data-contract-boundaries.md.
 */

import { z } from 'zod'

import { ednodaLanguageCodeSchema } from '@/schemas/language/languageSchema'
import { sourceDocumentTargetSchema } from '@/schemas/source-documents/source-document'
import {
  isoDateTimeSchema,
  nonNegativeIntSchema,
  positiveIntSchema,
  sourceDocumentEnvironmentSchema,
  sourceDocumentIdSchema,
  sourceDocumentS3BucketSchema,
  sourceDocumentS3KeySchema,
  sourceDocumentS3PointerSchema,
  sourceDocumentWorkflowOriginalSchema,
} from '@/schemas/source-documents/source-document-contracts'
import {
  ExtractionStrategy,
  SourceDocumentExtractionStatus,
  SourceDocumentWorkflowMode,
} from '@/schemas/source-documents/source-document-enums'

/** Full MVP manifest may include `partial`; Alpha workers emit only ready, failed, ocr_required. */
const extractedSourceDocumentManifestExtractionStatusSchema = z.enum([
  SourceDocumentExtractionStatus.ready,
  SourceDocumentExtractionStatus.partial,
  SourceDocumentExtractionStatus.failed,
  SourceDocumentExtractionStatus.ocrRequired,
])

const extractedSourceDocumentManifestExtractionStrategySchema = z.enum([
  ExtractionStrategy.pdfTextLayer,
  ExtractionStrategy.docx,
  ExtractionStrategy.pptx,
  ExtractionStrategy.csv,
  ExtractionStrategy.plainText,
  ExtractionStrategy.docConverted,
  ExtractionStrategy.pptConverted,
  ExtractionStrategy.ocr,
])

const extractedSourceDocumentLanguageSchema = z.enum([
  'en',
  'ko',
  'mixed',
  'unknown',
])

const extractedSourceDocumentBlockTypeSchema = z.enum([
  'heading',
  'paragraph',
  'table',
  'table_header',
  'table_row',
  'list',
  'slide',
  'slide_text',
  'speaker_notes',
  'footer',
  'unknown',
])

const extractedSourceDocumentImportanceHintSchema = z.enum([
  'high',
  'medium',
  'low',
  'unknown',
])

const extractedSourceDocumentManifestBlockIndexItemSchema = z
  .object({
    blockId: z.string().min(1),
    bucket: sourceDocumentS3BucketSchema,
    key: sourceDocumentS3KeySchema,
    blockType: extractedSourceDocumentBlockTypeSchema,
    sourcePageNumber: positiveIntSchema.optional(),
    sourceSlideNumber: positiveIntSchema.optional(),
    sourceRowNumber: nonNegativeIntSchema.optional(),
    charCount: nonNegativeIntSchema,
    detectedLanguage: extractedSourceDocumentLanguageSchema.optional(),
    importanceHint: extractedSourceDocumentImportanceHintSchema.optional(),
  })
  .strict()

const extractedSourceDocumentManifestChunkItemSchema = z
  .object({
    chunkId: z.string().min(1),
    bucket: sourceDocumentS3BucketSchema,
    key: sourceDocumentS3KeySchema,
    index: nonNegativeIntSchema,
    charStart: nonNegativeIntSchema,
    charEnd: nonNegativeIntSchema,
    sourceBlockIds: z.array(z.string().min(1)),
  })
  .strict()

export const extractedSourceDocumentManifestV1Schema = z
  .object({
    version: z.literal('ednoda.extracted-source-document.v1'),
    document: z
      .object({
        sourceDocumentId: sourceDocumentIdSchema,
        extractionId: positiveIntSchema,
        originalFilename: z.string().min(1).max(512),
        originalMimeType: z.string().min(1).max(255),
        fileExtension: z.string().min(1).max(32),
        originalBucket: sourceDocumentS3BucketSchema,
        originalKey: sourceDocumentS3KeySchema,
      })
      .strict(),
    extraction: z
      .object({
        status: extractedSourceDocumentManifestExtractionStatusSchema,
        extractionStrategy:
          extractedSourceDocumentManifestExtractionStrategySchema,
        charCount: nonNegativeIntSchema,
        blockCount: nonNegativeIntSchema,
        chunkCount: nonNegativeIntSchema,
        pageCount: positiveIntSchema.optional(),
        slideCount: positiveIntSchema.optional(),
        tableCount: nonNegativeIntSchema.optional(),
        detectedLanguages: z.array(ednodaLanguageCodeSchema),
        warnings: z.array(z.string()),
      })
      .strict(),
    outputs: z
      .object({
        plainText: sourceDocumentS3PointerSchema,
        blockIndex: z.array(
          extractedSourceDocumentManifestBlockIndexItemSchema,
        ),
        chunks: z.array(extractedSourceDocumentManifestChunkItemSchema),
      })
      .strict(),
  })
  .strict()

export type ExtractedSourceDocumentManifestV1 = z.infer<
  typeof extractedSourceDocumentManifestV1Schema
>

const extractedSourceDocumentBlockSourceSchema = z
  .object({
    pageNumber: positiveIntSchema.optional(),
    slideNumber: positiveIntSchema.optional(),
    rowNumber: nonNegativeIntSchema.optional(),
  })
  .strict()

export const extractedSourceDocumentBlockV1Schema = z
  .object({
    version: z.literal('ednoda.extracted-source-document-block.v1'),
    sourceDocumentId: sourceDocumentIdSchema,
    extractionId: positiveIntSchema,
    blockId: z.string().min(1),
    source: extractedSourceDocumentBlockSourceSchema,
    blockType: extractedSourceDocumentBlockTypeSchema,
    text: z.string(),
    table: z
      .object({
        rows: z.array(z.array(z.string())),
      })
      .strict()
      .optional(),
    detectedLanguage: extractedSourceDocumentLanguageSchema.optional(),
    importanceHint: extractedSourceDocumentImportanceHintSchema.optional(),
  })
  .strict()

export type ExtractedSourceDocumentBlockV1 = z.infer<
  typeof extractedSourceDocumentBlockV1Schema
>

export const sourceDocumentWorkflowInputV1Schema = z
  .object({
    version: z.literal('source-document-workflow.v1'),
    environment: sourceDocumentEnvironmentSchema,
    sourceDocumentId: sourceDocumentIdSchema,
    ownerUserId: z.string().uuid(),
    target: sourceDocumentTargetSchema,
    original: sourceDocumentWorkflowOriginalSchema,
    requestedAtIso: isoDateTimeSchema,
    attemptNumber: positiveIntSchema,
    workflowMode: z.enum([
      SourceDocumentWorkflowMode.full,
      SourceDocumentWorkflowMode.previewOnly,
      SourceDocumentWorkflowMode.extractionOnly,
    ]),
    workflowExecutionRowId: positiveIntSchema.optional(),
  })
  .strict()

export type SourceDocumentWorkflowInputV1 = z.infer<
  typeof sourceDocumentWorkflowInputV1Schema
>
