import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, type Router } from 'vue-router'
import { afterEach, vi } from 'vitest'

import type { ApiClient } from '@/api'
import App from '@/app/App.vue'
import { createAppI18n, type AppLocale } from '@/app/i18n'
import { createQueryClient } from '@/app/queryClient'
import { createAppRouter } from '@/app/router'
import { API_CLIENT_KEY } from '@/composables/useApiClient'

// The fixture locale also establishes browser fallback for account locale null and anonymous visitors.
let restoreBrowserLanguages: (() => void) | undefined
const mountedApplications = new Set<() => void>()
afterEach(() => {
  for (const dispose of mountedApplications) dispose()
  restoreBrowserLanguages?.()
  restoreBrowserLanguages = undefined
})

/**
 * Mount the whole application at `path`, with the real router on an in-memory history.
 *
 * A caller that needs the router beforehand — to build a client whose `onUnauthorized` hook
 * navigates it, for instance — creates one and passes it in; everyone else gets a fresh default.
 * The helper owns teardown after each test. Explicit unmounting also disposes the query cache and
 * is safe to repeat, including in tests that additionally use `enableAutoUnmount`.
 */
export async function mountApplicationAt(
  path: string,
  locale: AppLocale,
  client: ApiClient,
  router: Router = createAppRouter(createMemoryHistory()),
) {
  restoreBrowserLanguages?.()
  const languageSpy = vi.spyOn(navigator, 'languages', 'get').mockReturnValue([locale])
  restoreBrowserLanguages = () => languageSpy.mockRestore()
  await router.push(path)
  await router.isReady()
  const queryClient = createQueryClient()
  const wrapper = mount(App, {
    attachTo: document.body,
    global: {
      plugins: [createPinia(), createAppI18n(locale), router, [VueQueryPlugin, { queryClient }]],
      provide: { [API_CLIENT_KEY as symbol]: client },
    },
  })
  const unmount = wrapper.unmount.bind(wrapper)
  function dispose(): void {
    if (!mountedApplications.delete(dispose)) return
    try {
      unmount()
    } finally {
      queryClient.clear()
    }
  }
  mountedApplications.add(dispose)
  wrapper.unmount = dispose
  await flushPromises()
  return wrapper
}

/** Find a portalled dialog by the accessible name supplied by its visible title. */
export function queryDialogByName(name: string): HTMLElement | null {
  return (
    Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]')).find((dialog) => {
      const label = dialog.getAttribute('aria-label')
      const title = dialog
        .getAttribute('aria-labelledby')
        ?.split(/\s+/)
        .map((id) => document.getElementById(id)?.textContent ?? '')
        .join(' ')
      return (label ?? title)?.replace(/\s+/g, ' ').trim() === name
    }) ?? null
  )
}

/** These application dialog actions are native buttons named by visible text. */
export function getDialogButtonByName(dialogName: string, buttonName: string): HTMLButtonElement {
  const dialog = queryDialogByName(dialogName)
  const button = Array.from(dialog?.querySelectorAll('button') ?? []).find(
    (candidate) =>
      (candidate.getAttribute('aria-label') ?? candidate.textContent)
        ?.replace(/\s+/g, ' ')
        .trim() === buttonName,
  )
  if (button === undefined) throw new Error(`Missing dialog action: ${dialogName} / ${buttonName}`)
  return button
}
