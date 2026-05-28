/**
 * Dev/trusted-Alpha local candidate stub dispatch (task 10.6b harness boundary).
 * Mirrors `workers/source-documents/candidate-extractor-stub/ubc_local_adapter.py`.
 * Real UBC/external dispatch remains deferred (task 10.6).
 */

import type {
  SourceDocumentCandidateExtractionInputV1,
  SourceDocumentCandidateExtractionOutputCandidate,
  SourceDocumentCandidateExtractionOutputV1,
} from '../../../src/schemas/source-documents/source-document-candidate-extraction'

import { isoTimestamp } from './handler-util'
import { tryPostNodeCandidatesCallbackToUrl } from './post-source-document-callback'

const DEV_STUB_ENVIRONMENTS = new Set(['dev', 'staging', 'demo'])
const WARNING_UBC_LOCAL_STUB_DUMMY = 'ubc_local_stub_dummy_response'

export function isDevCandidateStubDispatchEnabled(
  handoff: SourceDocumentCandidateExtractionInputV1,
): boolean {
  return DEV_STUB_ENVIRONMENTS.has(handoff.environment)
}

export function buildDevStubCandidateExtractionResult(
  handoff: SourceDocumentCandidateExtractionInputV1,
): Pick<
  SourceDocumentCandidateExtractionOutputV1,
  'status' | 'candidates' | 'warnings' | 'error'
> {
  const documentId = handoff.sourceDocumentId
  const extractionId = handoff.extractionId
  const filename = handoff.original.filename

  const candidates: SourceDocumentCandidateExtractionOutputCandidate[] = [
    {
      candidateType: 'vocab',
      text: `${filename}: ubc-local-stub vocabulary`,
      normalizedText: `doc-${documentId}-ext-${extractionId}-vocab`,
      promptText: null,
      answerText: null,
      sourceBlockId: null,
      sourcePageNumber: null,
      sourceSlideNumber: null,
      confidence: 1,
      metadata: {
        source: 'ubc_local_stub',
        mode: 'dummy',
        environment: handoff.environment,
      },
    },
    {
      candidateType: 'question',
      text: `What did ubc-local-stub extract from document ${documentId}?`,
      normalizedText: `doc-${documentId}-ext-${extractionId}-question`,
      promptText: `What did ubc-local-stub extract from document ${documentId}?`,
      answerText: 'Deterministic stub answer (not from S3).',
      sourceBlockId: null,
      sourcePageNumber: null,
      sourceSlideNumber: null,
      confidence: 1,
      metadata: {
        source: 'ubc_local_stub',
        mode: 'dummy',
      },
    },
  ]

  return {
    status: 'ready',
    candidates,
    warnings: [WARNING_UBC_LOCAL_STUB_DUMMY],
    error: null,
  }
}

export function buildUbcNodeCandidatesCallbackBody(
  handoff: SourceDocumentCandidateExtractionInputV1,
  result: Pick<
    SourceDocumentCandidateExtractionOutputV1,
    'status' | 'candidates' | 'warnings' | 'error'
  >,
  attemptNumber: number,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    version: 'source-document-candidate-extraction-result.v1',
    sourceDocumentId: handoff.sourceDocumentId,
    extractionId: handoff.extractionId,
    attemptNumber,
    occurredAtIso: isoTimestamp(),
    status: result.status,
    candidates: result.candidates,
  }

  if (handoff.callback.taskToken) {
    body.taskToken = handoff.callback.taskToken
  }

  if (result.warnings && result.warnings.length > 0) {
    body.warnings = result.warnings
  }

  if (result.error) {
    body.error = result.error
  }

  return body
}

export async function dispatchDevCandidateStub(params: {
  handoff: SourceDocumentCandidateExtractionInputV1
  attemptNumber: number
}): Promise<{
  extractionResult: Pick<
    SourceDocumentCandidateExtractionOutputV1,
    'status' | 'candidates' | 'warnings' | 'error'
  >
  callbackBody: Record<string, unknown>
  callbackPosted: boolean
}> {
  const extractionResult = buildDevStubCandidateExtractionResult(params.handoff)
  const callbackBody = buildUbcNodeCandidatesCallbackBody(
    params.handoff,
    extractionResult,
    params.attemptNumber,
  )

  const postCallback = tryPostNodeCandidatesCallbackToUrl(
    params.handoff.callback.url,
    callbackBody,
  )

  if (postCallback) {
    await postCallback
    return {
      extractionResult,
      callbackBody,
      callbackPosted: true,
    }
  }

  return {
    extractionResult,
    callbackBody,
    callbackPosted: false,
  }
}
