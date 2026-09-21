import { createApp, type App as VueApp } from 'vue'

import App from './App.vue'
import {
  applyDocumentLanguage,
  createAppI18n,
  LOCALE_STORAGE_KEY,
  resolveInitialLocale,
} from './i18n'

function readStoredLocale(storage: Storage): string | null {
  try {
    return storage.getItem(LOCALE_STORAGE_KEY)
  } catch {
    // Storage can be blocked (private windows, site-data settings); the preference is only a convenience.
    return null
  }
}

/** Compose the application: plugins are registered here, and nowhere else. */
export function createApplication(environment: {
  storage: Storage
  languages: readonly string[]
  root: HTMLElement
}): VueApp {
  const locale = resolveInitialLocale({
    stored: readStoredLocale(environment.storage),
    languages: environment.languages,
  })
  applyDocumentLanguage(locale, environment.root)
  return createApp(App).use(createAppI18n(locale))
}
