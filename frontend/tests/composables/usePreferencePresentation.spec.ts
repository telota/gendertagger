import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createApiClient, type ApiClient } from '@/api'
import { createAppI18n, LOCALE_STORAGE_KEY } from '@/app/i18n'
import { createQueryClient } from '@/app/queryClient'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { useLocale, type UseLocale } from '@/composables/useLocale'
import { usePreferencePresentation } from '@/composables/usePreferencePresentation'
import { useTheme, type UseTheme } from '@/composables/useTheme'
import {
  useUserPreferences,
  userPreferencesQueryKey,
  type UserPreferences,
} from '@/composables/useUserPreferences'
import { useSessionStore, type CurrentUser } from '@/stores/session'

const USER_A: CurrentUser = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Account A',
  roles: [],
}
const USER_B: CurrentUser = { ...USER_A, id: 'b0000000-0000-0000-0000-000000000002' }
const DEFAULTS: UserPreferences = {
  locale: null,
  theme: 'system',
  desktop_sidebar_collapsed: false,
  revision: 0,
}
const ACCOUNT_A: UserPreferences = {
  locale: 'en',
  theme: 'dark',
  desktop_sidebar_collapsed: true,
  revision: 4,
}
const THEME_STORAGE_KEY = 'gendertagger.theme'
const wrappers: VueWrapper[] = []

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function mountPresentation(
  client: ApiClient,
  options: { user?: CurrentUser; mustChangePassword?: boolean; status?: 'idle' | 'ready' } = {},
) {
  let session!: ReturnType<typeof useSessionStore>
  let presentation!: ReturnType<typeof usePreferencePresentation>
  let preferences!: ReturnType<typeof useUserPreferences>
  let locale!: UseLocale
  let theme!: UseTheme
  const queryClient = createQueryClient()
  const wrapper = mount(
    defineComponent({
      setup() {
        session = useSessionStore()
        session.$patch({
          user: options.user ?? null,
          status: options.status ?? 'ready',
          mustChangePassword: options.mustChangePassword ?? false,
        })
        presentation = usePreferencePresentation()
        preferences = useUserPreferences()
        locale = useLocale()
        theme = useTheme()
        return () => null
      },
    }),
    {
      global: {
        plugins: [createPinia(), createAppI18n('en'), [VueQueryPlugin, { queryClient }]],
        provide: { [API_CLIENT_KEY as symbol]: client },
      },
    },
  )
  wrappers.push(wrapper)
  return { wrapper, session, presentation, preferences, locale, theme, queryClient }
}

function effectiveTheme() {
  return document.documentElement.dataset.theme
}

beforeEach(() => {
  vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['de-DE'])
})

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  localStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.documentElement.lang = ''
  delete document.documentElement.dataset.theme
})

describe('usePreferencePresentation', () => {
  it('retains anonymous startup presentation until the session resolves', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    const fetch = vi.fn(() => Promise.resolve(json(DEFAULTS)))
    const { locale, session } = mountPresentation(createApiClient({ fetch }), { status: 'idle' })

    expect(locale.current.value).toBe('en')
    expect(effectiveTheme()).toBe('dark')
    expect(fetch).not.toHaveBeenCalled()
    session.status = 'ready'
    expect(locale.current.value).toBe('de')
  })

  it('keeps legacy choices anonymous and restores them after an account session', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    const pending = deferredResponse()
    const fetch = vi.fn(() => pending.promise)
    const { session, locale, theme, presentation } = mountPresentation(createApiClient({ fetch }))
    expect(locale.current.value).toBe('en')
    expect(effectiveTheme()).toBe('dark')
    expect(fetch).not.toHaveBeenCalled()

    session.user = USER_A
    expect(locale.current.value).toBe('de')
    expect(effectiveTheme()).toBe('light')
    expect(presentation.desktopSidebarCollapsed.value).toBe(false)
    pending.resolve(json({ ...DEFAULTS, locale: 'de', theme: 'light' }))
    await flushPromises()
    expect(locale.current.value).toBe('de')
    expect(theme.preference.value).toBe('light')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(fetch).toHaveBeenCalledTimes(1)

    session.forgetSession()
    expect(locale.current.value).toBe('en')
    expect(effectiveTheme()).toBe('dark')
  })

  it('applies canonical defaults and follows browser changes without resolving the saved values', async () => {
    let prefersDark = false
    const listeners = new Set<() => void>()
    vi.stubGlobal('matchMedia', () => ({
      get matches() {
        return prefersDark
      },
      addEventListener: (_event: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_event: string, listener: () => void) => listeners.delete(listener),
    }))
    localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    const fetch = vi.fn(() => Promise.resolve(json(DEFAULTS)))
    const { locale, theme, queryClient } = mountPresentation(createApiClient({ fetch }), {
      user: USER_A,
    })
    await flushPromises()
    expect(locale.current.value).toBe('de')
    expect(effectiveTheme()).toBe('light')

    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['fr', 'en-GB'])
    window.dispatchEvent(new Event('languagechange'))
    prefersDark = true
    for (const listener of listeners) listener()

    expect(locale.current.value).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    expect(theme.preference.value).toBe('system')
    expect(effectiveTheme()).toBe('dark')
    expect(queryClient.getQueryData(userPreferencesQueryKey(USER_A.id))).toEqual(DEFAULTS)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('applies the canonical save response rather than the submitted draft', async () => {
    const saved = { ...ACCOUNT_A, locale: 'en' as const, theme: 'dark' as const, revision: 1 }
    const fetch = vi.fn((request: Request) =>
      Promise.resolve(json(request.method === 'PATCH' ? saved : DEFAULTS)),
    )
    const { locale, theme, preferences, presentation } = mountPresentation(
      createApiClient({ fetch }),
      { user: USER_A },
    )
    await flushPromises()

    const result = await preferences.save({
      locale: 'de',
      theme: 'light',
      desktop_sidebar_collapsed: false,
      expected_revision: 0,
    })
    await flushPromises()

    expect(result.status).toBe('success')
    expect(locale.current.value).toBe('en')
    expect(theme.preference.value).toBe('dark')
    expect(presentation.desktopSidebarCollapsed.value).toBe(true)
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBeNull()
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
  })

  it('does not apply a failed save or fall back to anonymous choices after a failed read', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    const fetch = vi.fn(() => Promise.reject(new TypeError('Network unavailable')))
    const { locale, theme, preferences } = mountPresentation(createApiClient({ fetch }), {
      user: USER_A,
    })
    await flushPromises()

    expect(preferences.query.isError.value).toBe(true)
    expect(locale.current.value).toBe('de')
    expect(theme.preference.value).toBe('system')
    const result = await preferences.save({
      locale: 'en',
      theme: 'dark',
      desktop_sidebar_collapsed: true,
      expected_revision: 0,
    })
    expect(result.status).toBe('failure')
    expect(locale.current.value).toBe('de')
    expect(effectiveTheme()).toBe('light')
  })

  it('clears account presentation synchronously and ignores pending responses after switching accounts', async () => {
    const pending = deferredResponse()
    let reads = 0
    const fetch = vi.fn(() => {
      reads += 1
      return reads === 1 ? Promise.resolve(json(ACCOUNT_A)) : pending.promise
    })
    const { session, locale, theme, presentation, queryClient } = mountPresentation(
      createApiClient({ fetch }),
      { user: USER_A },
    )
    await flushPromises()
    expect(locale.current.value).toBe('en')
    expect(effectiveTheme()).toBe('dark')
    expect(presentation.desktopSidebarCollapsed.value).toBe(true)

    session.user = USER_B
    expect(locale.current.value).toBe('de')
    expect(theme.preference.value).toBe('system')
    expect(presentation.desktopSidebarCollapsed.value).toBe(false)
    await flushPromises()
    session.forgetSession()
    pending.resolve(json(ACCOUNT_A))
    await flushPromises()

    expect(locale.current.value).toBe('de')
    expect(theme.preference.value).toBe('system')
    expect(presentation.desktopSidebarCollapsed.value).toBe(false)
    expect(queryClient.getQueryData(userPreferencesQueryKey(USER_A.id))).toBeUndefined()
    expect(queryClient.getQueryData(userPreferencesQueryKey(USER_B.id))).toBeUndefined()
  })

  it('ignores account A reads that finish after account B values have already applied', async () => {
    const late = deferredResponse()
    let reads = 0
    const fetch = vi.fn(() => {
      reads += 1
      return reads === 1 ? late.promise : Promise.resolve(json({ ...DEFAULTS, theme: 'light' }))
    })
    const { session, locale, theme } = mountPresentation(createApiClient({ fetch }), {
      user: USER_A,
    })
    await flushPromises()
    session.user = USER_B
    await flushPromises()
    late.resolve(json(ACCOUNT_A))
    await flushPromises()

    expect(locale.current.value).toBe('de')
    expect(theme.preference.value).toBe('light')
  })

  it('uses defaults without a preferences request until forced password change is complete', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    const fetch = vi.fn(() => Promise.resolve(json(ACCOUNT_A)))
    const { session, locale, theme } = mountPresentation(createApiClient({ fetch }), {
      user: USER_A,
      mustChangePassword: true,
    })
    await flushPromises()

    expect(fetch).not.toHaveBeenCalled()
    expect(locale.current.value).toBe('de')
    expect(theme.preference.value).toBe('system')
    session.mustChangePassword = false
    await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(locale.current.value).toBe('en')
    expect(theme.preference.value).toBe('dark')
  })
})
