import { createHmac } from 'crypto'

const SOURCE_DOCUMENT_WORKER_USER_AGENT = 'EdnodaSourceDocumentWorker/1.0'

function signCallbackBody(secret: string, rawBody: string): string {
  return createHmac('sha256', secret).update(rawBody, 'utf8').digest('hex')
}

export async function postSourceDocumentCallback(params: {
  baseUrl: string
  secret: string
  path: string
  body: Record<string, unknown>
}): Promise<void> {
  const url = new URL(params.path, params.baseUrl).toString()
  const rawBody = JSON.stringify(params.body)
  const signature = signCallbackBody(params.secret, rawBody)

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-ednoda-signature': signature,
      'user-agent': SOURCE_DOCUMENT_WORKER_USER_AGENT,
    },
    body: rawBody,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(
      `Source document callback failed (${response.status}): ${text}`,
    )
  }
}

export function tryPostMalwareScanCallback(
  body: Record<string, unknown>,
): Promise<void> | null {
  const baseUrl = process.env.EDNODA_CALLBACK_BASE_URL
  const secret = process.env.SOURCE_DOCUMENT_CALLBACK_SECRET

  if (!baseUrl || !secret) {
    return null
  }

  return postSourceDocumentCallback({
    baseUrl,
    secret,
    path: '/api/source-documents/malware-scan/callback',
    body,
  })
}

export function tryPostWorkflowCallback(
  body: Record<string, unknown>,
): Promise<void> | null {
  const baseUrl = process.env.EDNODA_CALLBACK_BASE_URL
  const secret = process.env.SOURCE_DOCUMENT_CALLBACK_SECRET

  if (!baseUrl || !secret) {
    return null
  }

  return postSourceDocumentCallback({
    baseUrl,
    secret,
    path: '/api/source-documents/workflow/callback',
    body,
  })
}

export async function postNodeCandidatesCallbackToUrl(
  callbackUrl: string,
  secret: string,
  body: Record<string, unknown>,
): Promise<void> {
  const url = new URL(callbackUrl)
  const rawBody = JSON.stringify(body)
  const signature = signCallbackBody(secret, rawBody)

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-ednoda-signature': signature,
      'user-agent': SOURCE_DOCUMENT_WORKER_USER_AGENT,
    },
    body: rawBody,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(
      `Source document node-candidates callback failed (${response.status}): ${text}`,
    )
  }
}

export function tryPostNodeCandidatesCallbackToUrl(
  callbackUrl: string,
  body: Record<string, unknown>,
): Promise<void> | null {
  const secret = process.env.SOURCE_DOCUMENT_CALLBACK_SECRET

  if (!callbackUrl || !secret) {
    return null
  }

  return postNodeCandidatesCallbackToUrl(callbackUrl, secret, body)
}
