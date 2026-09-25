import { computed, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  applyDocumentLanguage,
  DEFAULT_LOCALE,
  isAppLocale,
  LOCALE_STORAGE_KEY,
  resolveInitialLocale,
  SUPPORTED_LOCALES,
  type AppLocale,
} from '@/app/i18n'

export interface LocaleOption {
  value: AppLocale
  label: string
}

// Language names are autonyms and remain identifiable in either interface language.
const LOCALE_LABELS: Record<AppLocale, string> = {
  de: 'Deutsch',
  en: 'English',
}

// Only anonymous choices live here; canonical account preferences remain in the query cache.
// Keying by the app's global composer shares anonymous choices between root and header controls.
const anonymousChoices = new WeakMap<object, { locale: AppLocale | null }>()

function readAnonymousLocale(): AppLocale | null {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY)
    return isAppLocale(stored) ? stored : null
  } catch {
    return null
  }
}

export interface UseLocale {
  current: ComputedRef<AppLocale>
  options: readonly LocaleOption[]
  /** Change the anonymous browser choice, including its local persistence. */
  setLocale: (value: AppLocale) => void
  /** Apply a confirmed account choice without changing anonymous browser storage. */
  applyLocale: (value: AppLocale | null) => void
  restoreAnonymousLocale: () => void
}

/** Resolve effective interface language without conflating anonymous and account ownership. */
export function useLocale(): UseLocale {
  const composer = useI18n({ useScope: 'global' })
  const { locale } = composer
  let anonymous = anonymousChoices.get(composer)
  if (!anonymous) {
    anonymous = { locale: readAnonymousLocale() }
    anonymousChoices.set(composer, anonymous)
  }
  const anonymousChoice = anonymous
  const options = SUPPORTED_LOCALES.map((value) => ({ value, label: LOCALE_LABELS[value] }))

  function applyLocale(value: AppLocale | null): void {
    const effective = resolveInitialLocale({ stored: value, languages: navigator.languages })
    locale.value = effective
    applyDocumentLanguage(effective, document.documentElement)
  }

  function setLocale(value: AppLocale): void {
    anonymousChoice.locale = value
    applyLocale(value)
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, value)
    } catch {
      // Retain the anonymous choice in memory even when browser storage is blocked.
    }
  }

  function restoreAnonymousLocale(): void {
    applyLocale(anonymousChoice.locale)
  }

  const current = computed<AppLocale>(() =>
    isAppLocale(locale.value) ? locale.value : DEFAULT_LOCALE,
  )

  return { current, options, setLocale, applyLocale, restoreAnonymousLocale }
}
