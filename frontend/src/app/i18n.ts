import { createI18n } from 'vue-i18n'

import de from '@/locales/de.json'
import en from '@/locales/en.json'

// Decision D3: the interface is bilingual from the first milestone. Canonical labels, tier names,
// statuses and identifiers are rendered from their tokens and are never part of these catalogues.
export const SUPPORTED_LOCALES = ['de', 'en'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]

export const DEFAULT_LOCALE: AppLocale = 'de'
const FALLBACK_LOCALE: AppLocale = 'en'
export const LOCALE_STORAGE_KEY = 'gendertagger.locale'

type MessageSchema = typeof en

const numberFormats = {
  integer: { maximumFractionDigits: 0 },
  decimal: { minimumFractionDigits: 1, maximumFractionDigits: 1 },
  // Rates and coefficients of the evaluation report keep the three places the report itself stores.
  ratio: { minimumFractionDigits: 3, maximumFractionDigits: 3 },
  // A method's own confidence keeps two places: rounding 0.42 to 0.4 would misreport it.
  confidence: { minimumFractionDigits: 2, maximumFractionDigits: 2 },
  percent: { style: 'percent', maximumFractionDigits: 0 },
} as const

const datetimeFormats = {
  date: { dateStyle: 'medium' },
  timestamp: { dateStyle: 'medium', timeStyle: 'short' },
} as const

export function isAppLocale(value: unknown): value is AppLocale {
  return SUPPORTED_LOCALES.some((locale) => locale === value)
}

/**
 * Choose the starting locale: an explicit stored choice wins, then the first browser language whose
 * primary subtag is supported, then the default.
 */
export function resolveInitialLocale(input: {
  stored: string | null
  languages: readonly string[]
}): AppLocale {
  if (isAppLocale(input.stored)) return input.stored
  for (const language of input.languages) {
    const primary = language.toLowerCase().split('-')[0]
    if (isAppLocale(primary)) return primary
  }
  return DEFAULT_LOCALE
}

export function createAppI18n(locale: AppLocale) {
  return createI18n<[MessageSchema], AppLocale, false>({
    legacy: false,
    locale,
    fallbackLocale: FALLBACK_LOCALE,
    messages: { de, en },
    numberFormats: { de: numberFormats, en: numberFormats },
    datetimeFormats: { de: datetimeFormats, en: datetimeFormats },
  })
}

/** Keep the document language in step with the interface so assistive technology pronounces it. */
export function applyDocumentLanguage(locale: AppLocale, root: HTMLElement): void {
  root.lang = locale
}
