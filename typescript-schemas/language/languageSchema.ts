import { z } from 'zod'

import {
  EDNODA_LANGUAGE_CODES,
  SUPPORTED_LANGUAGE_CODES,
} from '@/utils/language/languageUtil'

/**
 * Zod schema for a valid BCP-47 language code supported by the translation system.
 */
export const languageCodeSchema = z.enum(SUPPORTED_LANGUAGE_CODES)

/**
 * Zod schema for any Ednoda content language (English source + translation targets).
 */
export const ednodaLanguageCodeSchema = z.enum(EDNODA_LANGUAGE_CODES)

/**
 * Zod schema for a nullable/optional target language code field.
 * Used on models like Classroom where the field is optional.
 */
export const optionalLanguageCodeSchema = languageCodeSchema
  .nullable()
  .optional()

export type LanguageCode = z.infer<typeof languageCodeSchema>
export type EdnodaLanguageCode = z.infer<typeof ednodaLanguageCodeSchema>
