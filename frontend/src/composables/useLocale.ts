import { computed, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  applyDocumentLanguage,
  DEFAULT_LOCALE,
  isAppLocale,
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  type AppLocale,
} from '@/app/i18n'

export interface LocaleOption {
  value: AppLocale
  label: string
}

// Each language's own name for itself (an autonym) is shown identically no matter which language
// is currently active — unlike the rest of the interface, this is not translated.
const LOCALE_LABELS: Record<AppLocale, string> = {
  de: 'Deutsch',
  en: 'English',
}

export interface UseLocale {
  current: ComputedRef<AppLocale>
  options: readonly LocaleOption[]
  setLocale: (value: AppLocale) => void
}

/** Switch the active interface language at runtime, keeping storage and `<html lang>` in step. */
export function useLocale(): UseLocale {
  const { locale } = useI18n({ useScope: 'global' })
  const options = SUPPORTED_LOCALES.map((value) => ({ value, label: LOCALE_LABELS[value] }))

  function setLocale(value: AppLocale): void {
    locale.value = value
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, value)
    } catch {
      // Storage can be blocked (private windows, site-data settings); the choice still applies
      // for the rest of this page's life.
    }
    applyDocumentLanguage(value, document.documentElement)
  }

  // `useI18n`'s scoped-global `locale` is typed as a plain string; it is only ever set through
  // `setLocale` below or the app's own bootstrap, both of which only ever use `AppLocale` values.
  const current = computed<AppLocale>(() =>
    isAppLocale(locale.value) ? locale.value : DEFAULT_LOCALE,
  )

  return { current, options, setLocale }
}
