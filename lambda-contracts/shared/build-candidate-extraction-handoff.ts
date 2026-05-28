/**
 * Builds SourceDocumentCandidateExtractionInputV1 from extraction pointers.
 * Passes S3 text package locations only — candidateType is assigned downstream by UBC/stub.
 */

import type { SourceDocumentCandidateExtractionInputV1 } from '../../../src/schemas/source-documents/source-document-candidate-extraction'

import { type CandidateHandoffInput } from './schemas'

const NODE_CANDIDATES_CALLBACK_PATH =
  '/api/source-documents/node-candidates/callback'

/** Last path segment of an Ednoda-owned S3 key (matches Python `filename_from_s3_key`). */
export function filenameFromS3Key(key: string): string {
  const segment = key.split('/').pop()
  return segment && segment.length > 0 ? segment : key
}

/** Derives block/chunk prefixes from a canonical `manifest.json` key. */
export function deriveTextPackagePrefixesFromManifestKey(manifestKey: string): {
  blocksPrefix: string
  chunksPrefix: string
} {
  const packagePrefix = manifestKey.replace(/\/manifest\.json$/, '')
  return {
    blocksPrefix: `${packagePrefix}/blocks/`,
    chunksPrefix: `${packagePrefix}/chunks/`,
  }
}

export function buildNodeCandidatesCallbackUrl(baseUrl: string): string {
  return new URL(NODE_CANDIDATES_CALLBACK_PATH, baseUrl).toString()
}

export function buildCandidateExtractionInputV1(params: {
  input: CandidateHandoffInput
  callbackBaseUrl: string
}): SourceDocumentCandidateExtractionInputV1 {
  const { input, callbackBaseUrl } = params
  const prefixes = deriveTextPackagePrefixesFromManifestKey(input.manifestKey)

  return {
    version: 'source-document-candidate-extraction.v1',
    environment: input.environment,
    sourceDocumentId: input.sourceDocumentId,
    extractionId: input.extractionId,
    target: input.target,
    extractedTextPackage: {
      manifest: { bucket: input.textBucket, key: input.manifestKey },
      plainText: { bucket: input.textBucket, key: input.plainTextKey },
      chunksPrefix: {
        bucket: input.textBucket,
        prefix: prefixes.chunksPrefix,
      },
      blocksPrefix: {
        bucket: input.textBucket,
        prefix: prefixes.blocksPrefix,
      },
    },
    original: {
      filename: filenameFromS3Key(input.original.key),
      mimeType: input.original.mimeType,
      fileExtension: input.original.fileExtension,
    },
    callback: {
      url: buildNodeCandidatesCallbackUrl(callbackBaseUrl),
      signingHeader: 'X-Ednoda-Signature',
      taskToken: input.taskToken ?? null,
    },
  }
}
