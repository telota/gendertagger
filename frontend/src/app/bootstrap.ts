import { createPinia } from 'pinia'
import { createApp, type App as VueApp } from 'vue'
import type { RouterHistory } from 'vue-router'

import { createApiClient } from '@/api'
import { API_CLIENT_KEY } from '@/composables/useApiClient'

import App from './App.vue'
import {
  applyDocumentLanguage,
  createAppI18n,
  LOCALE_STORAGE_KEY,
  resolveInitialLocale,
} from './i18n'
import { createAppRouter } from './router'

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
  /** Defaults to browser history; tests pass an in-memory history. */
  history?: RouterHistory
}): VueApp {
  const locale = resolveInitialLocale({
    stored: readStoredLocale(environment.storage),
    languages: environment.languages,
  })
  applyDocumentLanguage(locale, environment.root)
  const application = createApp(App)
  application.provide(API_CLIENT_KEY, createApiClient())
  return application
    .use(createPinia())
    .use(createAppI18n(locale))
    .use(createAppRouter(environment.history))
}
