import { VueQueryPlugin } from '@tanstack/vue-query'
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
import { createQueryClient } from './queryClient'
import { createAppRouter } from './router'
import { createUnauthorizedHandler, shouldRetryAfterUnauthorized } from './sessionGuard'

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
  const router = createAppRouter(environment.history)
  const application = createApp(App)
  // `createUnauthorizedHandler` only reads the session store once a 401 actually happens, well after
  // Pinia is installed below, so the ordering here is safe despite the store not existing yet.
  application.provide(
    API_CLIENT_KEY,
    createApiClient({
      onUnauthorized: createUnauthorizedHandler(router),
      shouldRetryAfterUnauthorized,
    }),
  )
  return application
    .use(createPinia())
    .use(createAppI18n(locale))
    .use(router)
    .use(VueQueryPlugin, { queryClient: createQueryClient() })
}
