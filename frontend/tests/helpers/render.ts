import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, type Router } from 'vue-router'

import type { ApiClient } from '@/api'
import App from '@/app/App.vue'
import { createAppI18n, type AppLocale } from '@/app/i18n'
import { createAppRouter } from '@/app/router'
import { API_CLIENT_KEY } from '@/composables/useApiClient'

/**
 * Mount the whole application at `path`, with the real router on an in-memory history.
 *
 * A caller that needs the router beforehand — to build a client whose `onUnauthorized` hook
 * navigates it, for instance — creates one and passes it in; everyone else gets a fresh default.
 */
export async function mountApplicationAt(
  path: string,
  locale: AppLocale,
  client: ApiClient,
  router: Router = createAppRouter(createMemoryHistory()),
) {
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, {
    attachTo: document.body,
    global: {
      plugins: [createPinia(), createAppI18n(locale), router],
      provide: { [API_CLIENT_KEY as symbol]: client },
    },
  })
  await flushPromises()
  return wrapper
}
