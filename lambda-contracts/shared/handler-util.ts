import type { z } from 'zod'

export function parseHandlerInput<TSchema extends z.ZodTypeAny>(
  schema: TSchema,
  event: unknown,
): z.infer<TSchema> {
  const result = schema.safeParse(event)

  if (!result.success) {
    throw new Error(
      `Invalid Lambda input: ${result.error.issues.map((issue) => issue.message).join('; ')}`,
    )
  }

  return result.data
}

export function isoTimestamp(): string {
  return new Date().toISOString()
}
