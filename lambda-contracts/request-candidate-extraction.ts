import { sourceDocumentCandidateExtractionInputV1Schema } from '../typescript-schemas/source-documents/source-document-candidate-extraction'

import { buildCandidateExtractionInputV1 } from './shared/build-candidate-extraction-handoff'
import {
  dispatchDevCandidateStub,
  isDevCandidateStubDispatchEnabled,
} from './shared/dispatch-dev-candidate-stub'
import { isoTimestamp, parseHandlerInput } from './shared/handler-util'
import { candidateHandoffInputSchema } from './shared/schemas'

/** Local UBC stub harness (task 10.6b) — Python reference; dev dispatch uses TS mirror. */
export const UBC_LOCAL_STUB_HARNESS_MODULE =
  'workers/source-documents/candidate-extractor-stub/ubc_local_adapter.py'

/**
 * Packages a compact candidate-extraction handoff payload (v1 contract) and, in
 * dev/staging/demo, dispatches the local UBC stub harness boundary (task 10.6b).
 * External UBC dispatch remains deferred to task 10.6.
 */
export const handler = async (event: unknown) => {
  const input = parseHandlerInput(candidateHandoffInputSchema, event)
  const callbackBaseUrl = process.env.EDNODA_CALLBACK_BASE_URL

  if (!callbackBaseUrl) {
    throw new Error('EDNODA_CALLBACK_BASE_URL is required')
  }

  const candidateExtractionInput =
    sourceDocumentCandidateExtractionInputV1Schema.parse(
      buildCandidateExtractionInputV1({
        input,
        callbackBaseUrl,
      }),
    )
  const requestedAtIso = isoTimestamp()
  const attemptNumber = input.attemptNumber ?? 1

  const baseResult = {
    sourceDocumentId: input.sourceDocumentId,
    workflowExecutionArn: input.workflowExecutionArn ?? null,
    workflowExecutionRowId: input.workflowExecutionRowId ?? null,
    attemptNumber: input.attemptNumber ?? null,
    taskToken: input.taskToken ?? null,
    requestedAtIso,
    candidateExtractionInput,
  }

  if (!isDevCandidateStubDispatchEnabled(candidateExtractionInput)) {
    return {
      ...baseResult,
      status: 'handoff_prepared',
      handoffMode: 'placeholder' as const,
      dispatchStatus: 'not_sent' as const,
      dispatch: {
        mechanism: 'deferred' as const,
        sendDeferredUntil: 'candidate-extraction-worker-handoff',
        localStubHarness: UBC_LOCAL_STUB_HARNESS_MODULE,
        localStubEntrypoint: 'run_ubc_local_stub_handoff',
      },
    }
  }

  const stubDispatch = await dispatchDevCandidateStub({
    handoff: candidateExtractionInput,
    attemptNumber,
  })

  if (!stubDispatch.callbackPosted) {
    throw new Error(
      'Dev candidate stub dispatch requires SOURCE_DOCUMENT_CALLBACK_SECRET and callback URL',
    )
  }

  return {
    ...baseResult,
    status: stubDispatch.extractionResult.status,
    handoffMode: 'ubc_local_stub' as const,
    dispatchStatus: 'sent' as const,
    candidateCount: stubDispatch.extractionResult.candidates.length,
    warnings: stubDispatch.extractionResult.warnings ?? [],
    dispatch: {
      mechanism: 'local_stub' as const,
      localStubHarness: UBC_LOCAL_STUB_HARNESS_MODULE,
      localStubEntrypoint: 'run_ubc_local_stub_handoff',
      realUbcDispatchDeferredUntil: 'task-10.6',
    },
  }
}
