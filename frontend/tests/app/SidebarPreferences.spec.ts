import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import SidebarPreferences from '@/app/SidebarPreferences.vue'
import { createAppI18n, LOCALE_STORAGE_KEY, type AppLocale } from '@/app/i18n'
import { createQueryClient } from '@/app/queryClient'
import { createAppRouter } from '@/app/router'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { usePreferencePresentation } from '@/composables/usePreferencePresentation'
import type { UserPreferences } from '@/composables/useUserPreferences'
import UserSettingsView from '@/features/settings/UserSettingsView.vue'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore, type CurrentUser } from '@/stores/session'

import { expectNoAxeViolations } from '../helpers/axe'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const
const USER: CurrentUser = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Account A',
  roles: [],
}
const USER_B: CurrentUser = { ...USER, id: 'a0000000-0000-0000-0000-000000000002' }
const SAVED: UserPreferences = {
  locale: 'en',
  theme: 'light',
  desktop_sidebar_collapsed: false,
  interface_mode: 'guided',
  revision: 7,
}
const THEME_STORAGE_KEY = 'gendertagger.theme'
const cleanups: (() => void)[] = []
type SessionState = Pick<
  ReturnType<typeof useSessionStore>,
  'status' | 'user' | 'mustChangePassword'
>

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function failure(status = 503, code = 'internal_error'): Response {
  return json({ error: { code, message: 'Private server details must not be displayed.' } }, status)
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

async function mountPreferences(
  locale: AppLocale,
  handler: (request: Request) => Response | Promise<Response>,
  options: {
    session?: Partial<SessionState>
    desktopCollapsed?: boolean
    mobile?: boolean
    presentation?: 'sidebar' | 'header'
    settings?: boolean
  } = {},
) {
  vi.spyOn(navigator, 'languages', 'get').mockReturnValue([locale])
  const queryClient = createQueryClient()
  const router = createAppRouter(createMemoryHistory())
  await router.push('/settings')
  await router.isReady()
  let session!: ReturnType<typeof useSessionStore>
  const wrapper = mount(
    defineComponent({
      setup() {
        session = useSessionStore()
        session.$patch({
          status: 'ready',
          user: null,
          mustChangePassword: false,
          ...options.session,
        })
        usePreferencePresentation()
        return () =>
          h('div', [
            h(SidebarPreferences, {
              desktopCollapsed: options.desktopCollapsed ?? false,
              mobile: options.mobile ?? false,
              presentation: options.presentation ?? 'sidebar',
            }),
            ...(options.settings ? [h(UserSettingsView)] : []),
          ])
      },
    }),
    {
      attachTo: document.body,
      global: {
        plugins: [createPinia(), createAppI18n(locale), router, [VueQueryPlugin, { queryClient }]],
        provide: {
          [API_CLIENT_KEY as symbol]: createApiClient({
            fetch: (request) => Promise.resolve(handler(request)),
          }),
        },
      },
    },
  )
  cleanups.push(() => {
    wrapper.unmount()
    queryClient.clear()
  })
  await flushPromises()
  return { wrapper, session, queryClient }
}

function control(wrapper: VueWrapper, key: 'locale' | 'theme') {
  return wrapper.get<HTMLButtonElement>(`.sidebar-preferences [data-preference="${key}"] button`)
}

async function choose(wrapper: VueWrapper, key: 'locale' | 'theme', label: string) {
  await control(wrapper, key).trigger('click')
  await waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
  const option = wrapper.findAll('[role="option"]').find((item) => item.text() === label)
  if (!option) throw new Error(`No ${key} choice labelled ${label}.`)
  await option.trigger('click')
  await flushPromises()
}

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
  localStorage.clear()
  document.body.replaceChildren()
  document.documentElement.lang = ''
  delete document.documentElement.dataset.theme
  vi.restoreAllMocks()
})

describe.each(['de', 'en'] as const)('sidebar preferences in %s', (locale) => {
  const messages = catalogues[locale]

  it.each([
    { label: 'expanded', desktopCollapsed: false, mobile: false, presentation: 'sidebar' as const },
    { label: 'rail', desktopCollapsed: true, mobile: false, presentation: 'sidebar' as const },
    {
      label: 'mobile drawer',
      desktopCollapsed: true,
      mobile: true,
      presentation: 'sidebar' as const,
    },
    {
      label: 'public header',
      desktopCollapsed: true,
      mobile: false,
      presentation: 'header' as const,
    },
  ])('keeps anonymous language and theme choices usable in the $label', async (presentation) => {
    const fetch = vi.fn(() => failure())
    const { wrapper } = await mountPreferences(locale, fetch, presentation)
    expect(control(wrapper, 'locale').attributes('aria-label')).toBe(messages.locale.label)
    expect(control(wrapper, 'theme').attributes('aria-label')).toBe(messages.theme.label)
    expect(wrapper.get('section').classes().includes('sidebar-preferences--collapsed')).toBe(
      presentation.presentation === 'sidebar' &&
        presentation.desktopCollapsed &&
        !presentation.mobile,
    )

    if (presentation.presentation === 'header') {
      expect(wrapper.get('section').classes()).toContain('sidebar-preferences--header')
      const button = control(wrapper, 'theme')
      expect(button.text()).toContain(messages.theme.label)
      expect(button.text()).toContain(messages.theme.system)
      await button.trigger('mouseenter')
      button.element.focus()
      await flushPromises()
      expect(document.querySelector('[role="tooltip"]')).toBeNull()
    }

    await choose(wrapper, 'theme', messages.theme.dark)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    await choose(wrapper, 'locale', locale === 'en' ? 'Deutsch' : 'English')
    expect(document.documentElement.lang).toBe(locale === 'en' ? 'de' : 'en')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe(locale === 'en' ? 'de' : 'en')
    expect(fetch).not.toHaveBeenCalled()
    await expectNoAxeViolations(wrapper.get('section').element)
  })

  it.each([
    { label: 'loading', state: { status: 'loading' } },
    { label: 'session error', state: { status: 'error', user: USER } },
    { label: 'forced password change', state: { mustChangePassword: true, user: USER } },
  ] satisfies { label: string; state: Partial<SessionState> }[])(
    'allows temporary changes during $label without writing either preference owner',
    async ({ state }) => {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale)
      localStorage.setItem(THEME_STORAGE_KEY, 'light')
      const fetch = vi.fn(() => failure())
      const { wrapper } = await mountPreferences(locale, fetch, { session: state })
      expect(wrapper.get('.sidebar-preferences-help').text()).toBe(
        messages.sidebarPreferences.temporary,
      )

      await choose(wrapper, 'theme', messages.theme.dark)
      await choose(wrapper, 'locale', locale === 'en' ? 'Deutsch' : 'English')

      expect(document.documentElement.dataset.theme).toBe('dark')
      expect(document.documentElement.lang).toBe(locale === 'en' ? 'de' : 'en')
      expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe(locale)
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
      expect(fetch).not.toHaveBeenCalled()
    },
  )

  it.each([
    { label: 'loading', state: { status: 'loading' } },
    { label: 'session error', state: { status: 'error', user: USER } },
    { label: 'forced password change', state: { mustChangePassword: true, user: USER } },
  ] satisfies { label: string; state: Partial<SessionState> }[])(
    'keeps header choices temporary during $label',
    async ({ state }) => {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale)
      localStorage.setItem(THEME_STORAGE_KEY, 'light')
      const fetch = vi.fn(() => failure())
      const { wrapper } = await mountPreferences(locale, fetch, {
        session: state,
        presentation: 'header',
        desktopCollapsed: true,
      })
      const help = wrapper.get('.sidebar-preferences-help')
      expect(help.text()).toBe(messages.sidebarPreferences.temporary)
      expect(control(wrapper, 'theme').attributes('aria-describedby')).toBe(help.attributes('id'))
      expect(wrapper.get('section').classes()).not.toContain('sidebar-preferences--collapsed')

      await choose(wrapper, 'theme', messages.theme.dark)
      await choose(wrapper, 'locale', locale === 'en' ? 'Deutsch' : 'English')

      expect(document.documentElement.dataset.theme).toBe('dark')
      expect(document.documentElement.lang).toBe(locale === 'en' ? 'de' : 'en')
      expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe(locale)
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
      expect(fetch).not.toHaveBeenCalled()
      await expectNoAxeViolations(wrapper.get('section').element)
    },
  )

  it('applies only the canonical save response and sends only the chosen field plus revision', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'system')
    const response = deferredResponse()
    const bodies: unknown[] = []
    const saved = { ...SAVED, locale }
    const { wrapper } = await mountPreferences(
      locale,
      async (request) => {
        if (request.method === 'GET') return json(saved)
        bodies.push(await request.json())
        return response.promise
      },
      { session: { user: USER } },
    )
    await waitFor(() => expect(control(wrapper, 'theme').element.disabled).toBe(false))

    await choose(wrapper, 'theme', messages.theme.dark)
    await waitFor(() => expect(bodies).toEqual([{ theme: 'dark', expected_revision: 7 }]))
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(control(wrapper, 'theme').element.disabled).toBe(true)
    expect(control(wrapper, 'locale').element.disabled).toBe(true)

    response.resolve(json({ ...saved, theme: 'dark', revision: 8 }))
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system')
    expect(wrapper.get('[role="status"]').text()).toBe(messages.userSettings.states.saved)
  })

  it('preserves browser-default language as null in a partial account update', async () => {
    const bodies: unknown[] = []
    const { wrapper } = await mountPreferences(
      locale,
      async (request) => {
        if (request.method === 'GET') return json({ ...SAVED, locale })
        bodies.push(await request.json())
        return json({ ...SAVED, locale: null, revision: 8 })
      },
      { session: { user: USER } },
    )
    await waitFor(() => expect(control(wrapper, 'locale').element.disabled).toBe(false))

    await choose(wrapper, 'locale', messages.userSettings.language.browserDefault)

    await waitFor(() => expect(bodies).toEqual([{ locale: null, expected_revision: 7 }]))
    expect(control(wrapper, 'locale').text()).toContain(
      messages.userSettings.language.browserDefault,
    )
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBeNull()
  })

  it('keeps the current presentation after failure and can reload an uncertain save', async () => {
    let reads = 0
    const { wrapper } = await mountPreferences(
      locale,
      (request) => {
        if (request.method !== 'GET') return failure()
        reads += 1
        return json({
          ...SAVED,
          locale,
          theme: reads === 1 ? 'light' : 'dark',
          revision: reads === 1 ? 7 : 8,
        })
      },
      { session: { user: USER } },
    )
    await waitFor(() => expect(control(wrapper, 'theme').element.disabled).toBe(false))

    await choose(wrapper, 'theme', messages.theme.dark)

    await waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe(messages.sidebarPreferences.saveError),
    )
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(control(wrapper, 'theme').element.disabled).toBe(false)
    expect(wrapper.text()).not.toContain('Private server details')
    expect(wrapper.get('.sidebar-preferences-retry').text()).toBe(messages.userSettings.reloadSaved)

    await wrapper.get('.sidebar-preferences-retry').trigger('click')

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(reads).toBe(2)
  })

  it('requires explicit reload after conflict and never replays the rejected change', async () => {
    const bodies: unknown[] = []
    let reads = 0
    const { wrapper } = await mountPreferences(
      locale,
      async (request) => {
        if (request.method === 'GET') {
          reads += 1
          return json({ ...SAVED, locale, revision: reads === 1 ? 7 : 8 })
        }
        bodies.push(await request.json())
        return failure(409, 'preferences_revision_conflict')
      },
      { session: { user: USER } },
    )
    await waitFor(() => expect(control(wrapper, 'theme').element.disabled).toBe(false))
    await choose(wrapper, 'theme', messages.theme.dark)
    await waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe(messages.sidebarPreferences.conflict),
    )
    expect(control(wrapper, 'theme').element.disabled).toBe(true)
    expect(reads).toBe(1)

    await wrapper.get('.sidebar-preferences-retry').trigger('click')
    await waitFor(() => expect(control(wrapper, 'theme').element.disabled).toBe(false))
    expect(reads).toBe(2)
    expect(bodies).toEqual([{ theme: 'dark', expected_revision: 7 }])
    expect(document.documentElement.dataset.theme).toBe('light')

    await choose(wrapper, 'theme', messages.theme.dark)
    await waitFor(() =>
      expect(bodies).toEqual([
        { theme: 'dark', expected_revision: 7 },
        { theme: 'dark', expected_revision: 8 },
      ]),
    )
  })

  it('offers retry when account preferences cannot be loaded', async () => {
    let reads = 0
    const { wrapper } = await mountPreferences(
      locale,
      () => {
        reads += 1
        return reads === 1 ? failure() : json({ ...SAVED, locale })
      },
      { session: { user: USER } },
    )
    await waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe(messages.userSettings.loadError),
    )
    expect(control(wrapper, 'theme').element.disabled).toBe(true)

    await wrapper.get('.sidebar-preferences-retry').trigger('click')

    await waitFor(() => expect(control(wrapper, 'theme').element.disabled).toBe(false))
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(reads).toBe(2)
  })

  it('retains the conflict gate when reloading fails', async () => {
    let reads = 0
    const { wrapper } = await mountPreferences(
      locale,
      (request) => {
        if (request.method !== 'GET') return failure(409, 'preferences_revision_conflict')
        reads += 1
        return reads === 1 ? json({ ...SAVED, locale }) : failure()
      },
      { session: { user: USER } },
    )
    await waitFor(() => expect(control(wrapper, 'theme').element.disabled).toBe(false))
    await choose(wrapper, 'theme', messages.theme.dark)
    await waitFor(() => expect(wrapper.find('.sidebar-preferences-retry').exists()).toBe(true))

    await wrapper.get('.sidebar-preferences-retry').trigger('click')
    await waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe(messages.sidebarPreferences.reloadError),
    )

    expect(control(wrapper, 'theme').element.disabled).toBe(true)
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('ignores a pending save from the previous account', async () => {
    const response = deferredResponse()
    let reads = 0
    const { wrapper, session, queryClient } = await mountPreferences(
      locale,
      (request) => {
        if (request.method !== 'GET') return response.promise
        reads += 1
        return json({
          ...SAVED,
          locale,
          theme: reads === 1 ? 'light' : 'system',
          revision: reads === 1 ? 7 : 2,
        })
      },
      { session: { user: USER } },
    )
    await waitFor(() => expect(control(wrapper, 'theme').element.disabled).toBe(false))
    await choose(wrapper, 'theme', messages.theme.dark)

    session.user = USER_B
    await waitFor(() => expect(control(wrapper, 'theme').text()).toContain(messages.theme.system))
    response.resolve(json({ ...SAVED, locale, theme: 'dark', revision: 8 }))
    await flushPromises()

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(control(wrapper, 'theme').text()).toContain(messages.theme.system)
    const cachedData = queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.state.data)
    expect(cachedData).not.toContainEqual({ ...SAVED, locale })
    expect(cachedData).not.toContainEqual({ ...SAVED, locale, theme: 'dark', revision: 8 })
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(reads).toBe(2)
  })

  it('leaves an unsaved settings-page draft intact after a footer save', async () => {
    const { wrapper } = await mountPreferences(
      locale,
      async (request) => {
        if (request.method === 'GET') return json({ ...SAVED, locale })
        const body = (await request.json()) as { theme: 'dark' }
        return json({ ...SAVED, locale, theme: body.theme, revision: 8 })
      },
      { session: { user: USER }, settings: true },
    )
    await waitFor(() => expect(wrapper.find('#user-settings-locale').exists()).toBe(true))
    const draftLocale = locale === 'en' ? 'de' : 'en'
    await wrapper.get('#user-settings-locale').setValue(draftLocale)

    await choose(wrapper, 'theme', messages.theme.dark)
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))

    expect(wrapper.get<HTMLSelectElement>('#user-settings-locale').element.value).toBe(draftLocale)
    expect(wrapper.get<HTMLSelectElement>('#user-settings-theme').element.value).toBe('light')
    expect(wrapper.get('.user-settings-status').text()).toBe(messages.userSettings.states.unsaved)
  })

  it.each(['sidebar', 'header'] as const)(
    'supports %s keyboard selection and Escape returns focus to the trigger',
    async (presentation) => {
      const { wrapper } = await mountPreferences(locale, () => failure(), {
        desktopCollapsed: true,
        presentation,
      })
      const button = control(wrapper, 'theme')
      button.element.focus()
      await button.trigger('keydown', { key: 'ArrowDown' })
      await waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
      await wrapper.get('[role="listbox"]').trigger('keydown', { key: 'End' })
      await wrapper.get('[role="listbox"]').trigger('keydown', { key: 'Enter' })
      await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))

      await button.trigger('click')
      await wrapper.get('[role="listbox"]').trigger('keydown', { key: 'Escape' })
      await waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(false))
      await waitFor(() => expect(document.activeElement).toBe(button.element))
    },
  )
})
