import { z } from 'zod'

/**
 * Shared Source Document enum const-unions.
 * Single source of truth for Sequelize models and Zod schemas (Phase 1+).
 */

export const SourceDocumentTargetType = {
  lesson: 'lesson',
  textbookUnit: 'textbook_unit',
} as const
export type SourceDocumentTargetType =
  (typeof SourceDocumentTargetType)[keyof typeof SourceDocumentTargetType]
export const sourceDocumentTargetTypeSchema = z.nativeEnum(
  SourceDocumentTargetType,
)

export const SourceDocumentKind = {
  teacherGuide: 'teacher_guide',
  textbookUnit: 'textbook_unit',
  worksheet: 'worksheet',
  slideDeck: 'slide_deck',
  csv: 'csv',
  plainText: 'plain_text',
  unknown: 'unknown',
} as const
export type SourceDocumentKind =
  (typeof SourceDocumentKind)[keyof typeof SourceDocumentKind]
export const sourceDocumentKindSchema = z.nativeEnum(SourceDocumentKind)

export const SourceDocumentUploadStatus = {
  uploadUrlCreated: 'upload_url_created',
  uploaded: 'uploaded',
  uploadFailed: 'upload_failed',
  deleted: 'deleted',
} as const
export type SourceDocumentUploadStatus =
  (typeof SourceDocumentUploadStatus)[keyof typeof SourceDocumentUploadStatus]
export const sourceDocumentUploadStatusSchema = z.nativeEnum(
  SourceDocumentUploadStatus,
)

export const SourceDocumentMalwareScanStatus = {
  notStarted: 'not_started',
  queued: 'queued',
  scanning: 'scanning',
  clean: 'clean',
  infected: 'infected',
  failed: 'failed',
  unsupported: 'unsupported',
} as const
export type SourceDocumentMalwareScanStatus =
  (typeof SourceDocumentMalwareScanStatus)[keyof typeof SourceDocumentMalwareScanStatus]
export const sourceDocumentMalwareScanStatusSchema = z.nativeEnum(
  SourceDocumentMalwareScanStatus,
)

export const SourceDocumentWorkflowStatus = {
  notStarted: 'not_started',
  running: 'running',
  completed: 'completed',
  completedWithErrors: 'completed_with_errors',
  blocked: 'blocked',
  failed: 'failed',
} as const
export type SourceDocumentWorkflowStatus =
  (typeof SourceDocumentWorkflowStatus)[keyof typeof SourceDocumentWorkflowStatus]
export const sourceDocumentWorkflowStatusSchema = z.nativeEnum(
  SourceDocumentWorkflowStatus,
)

export const SourceDocumentPreviewStatus = {
  notStarted: 'not_started',
  queued: 'queued',
  processing: 'processing',
  ready: 'ready',
  partial: 'partial',
  failed: 'failed',
  unsupported: 'unsupported',
} as const
export type SourceDocumentPreviewStatus =
  (typeof SourceDocumentPreviewStatus)[keyof typeof SourceDocumentPreviewStatus]
export const sourceDocumentPreviewStatusSchema = z.nativeEnum(
  SourceDocumentPreviewStatus,
)

export const SourceDocumentExtractionStatus = {
  notStarted: 'not_started',
  queued: 'queued',
  processing: 'processing',
  ready: 'ready',
  partial: 'partial',
  failed: 'failed',
  ocrRequired: 'ocr_required',
  unsupported: 'unsupported',
} as const
export type SourceDocumentExtractionStatus =
  (typeof SourceDocumentExtractionStatus)[keyof typeof SourceDocumentExtractionStatus]
export const sourceDocumentExtractionStatusSchema = z.nativeEnum(
  SourceDocumentExtractionStatus,
)

export const SourceDocumentNodeCandidateStatus = {
  notStarted: 'not_started',
  queued: 'queued',
  processing: 'processing',
  ready: 'ready',
  partial: 'partial',
  failed: 'failed',
} as const
export type SourceDocumentNodeCandidateStatus =
  (typeof SourceDocumentNodeCandidateStatus)[keyof typeof SourceDocumentNodeCandidateStatus]
export const sourceDocumentNodeCandidateStatusSchema = z.nativeEnum(
  SourceDocumentNodeCandidateStatus,
)

/** Production: GuardDuty Malware Protection for S3. Alpha/trusted env: mvp_stub only. */
export const MalwareScannerName = {
  guardDutyS3MalwareProtection: 'guardduty_s3_malware_protection',
  mvpStub: 'mvp_stub',
} as const
export type MalwareScannerName =
  (typeof MalwareScannerName)[keyof typeof MalwareScannerName]
export const malwareScannerNameSchema = z.nativeEnum(MalwareScannerName)

export const WorkflowExecutionStatus = {
  running: 'running',
  succeeded: 'succeeded',
  failed: 'failed',
  timedOut: 'timed_out',
  aborted: 'aborted',
} as const
export type WorkflowExecutionStatus =
  (typeof WorkflowExecutionStatus)[keyof typeof WorkflowExecutionStatus]
export const workflowExecutionStatusSchema = z.nativeEnum(
  WorkflowExecutionStatus,
)

export const SourceDocumentWorkflowMode = {
  full: 'full',
  previewOnly: 'preview_only',
  extractionOnly: 'extraction_only',
  candidateOnly: 'candidate_only',
  cleanup: 'cleanup',
} as const
export type SourceDocumentWorkflowMode =
  (typeof SourceDocumentWorkflowMode)[keyof typeof SourceDocumentWorkflowMode]
export const sourceDocumentWorkflowModeSchema = z.nativeEnum(
  SourceDocumentWorkflowMode,
)

export const PreviewStrategy = {
  pdfDirect: 'pdf_direct',
  convertedPdf: 'converted_pdf',
  pageImages: 'page_images',
  csvTable: 'csv_table',
  plainText: 'plain_text',
  unsupported: 'unsupported',
} as const
export type PreviewStrategy =
  (typeof PreviewStrategy)[keyof typeof PreviewStrategy]
export const previewStrategySchema = z.nativeEnum(PreviewStrategy)

export const ExtractionStrategy = {
  pdfTextLayer: 'pdf_text_layer',
  docx: 'docx',
  pptx: 'pptx',
  csv: 'csv',
  plainText: 'plain_text',
  docConverted: 'doc_converted',
  pptConverted: 'ppt_converted',
  ocr: 'ocr',
  unsupported: 'unsupported',
} as const
export type ExtractionStrategy =
  (typeof ExtractionStrategy)[keyof typeof ExtractionStrategy]
export const extractionStrategySchema = z.nativeEnum(ExtractionStrategy)

/**
 * Candidate extraction labels only — not used by text extraction or preview.
 * UBC/stub assigns these when posting node-candidates callbacks; text packages are
 * candidate-type-free. Values align with atomic EducationNode `nodeType` labels
 * (`vocab`, `expression`, `question`) plus `unknown`. `unknown` is stored for
 * review but is not convertible until the teacher sets a concrete type.
 */
export const NodeCandidateType = {
  vocab: 'vocab',
  expression: 'expression',
  question: 'question',
  unknown: 'unknown',
} as const
export type NodeCandidateType =
  (typeof NodeCandidateType)[keyof typeof NodeCandidateType]
export const nodeCandidateTypeSchema = z.nativeEnum(NodeCandidateType)

/** Postgres ENUM member list — matches {@link NodeCandidateType}. Used by Sequelize init only. */
export const nodeCandidateTypeDbValues = [
  ...Object.values(NodeCandidateType),
] as const

export const NodeCandidateReviewStatus = {
  suggested: 'suggested',
  accepted: 'accepted',
  rejected: 'rejected',
  edited: 'edited',
  convertedToEducationNode: 'converted_to_education_node',
} as const
export type NodeCandidateReviewStatus =
  (typeof NodeCandidateReviewStatus)[keyof typeof NodeCandidateReviewStatus]
export const nodeCandidateReviewStatusSchema = z.nativeEnum(
  NodeCandidateReviewStatus,
)

export const SourceDocumentCandidateConversionTargetType = {
  lessonNode: 'lesson_node',
  textbookNode: 'textbook_node',
} as const
export type SourceDocumentCandidateConversionTargetType =
  (typeof SourceDocumentCandidateConversionTargetType)[keyof typeof SourceDocumentCandidateConversionTargetType]
export const sourceDocumentCandidateConversionTargetTypeSchema = z.nativeEnum(
  SourceDocumentCandidateConversionTargetType,
)
