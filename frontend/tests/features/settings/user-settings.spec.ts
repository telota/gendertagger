import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import { createApiClient } from '@/api'
import { createAppI18n, type AppLocale } from '@/app/i18n'
import { createQueryClient } from '@/app/queryClient'
import { createAppRouter } from '@/app/router'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import type { UserPreferences } from '@/composables/useUserPreferences'
import UserSettingsView from '@/features/settings/UserSettingsView.vue'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore } from '@/stores/session'

import { expectNoAxeViolations } from '../../helpers/axe'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const
const USER_A = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'User A', roles: [] }
const USER_B = { id: 'a0000000-0000-0000-0000-000000000002', display_name: 'User B', roles: [] }
const DEFAULTS: UserPreferences = {
  locale: null,
  theme: 'system',
  desktop_sidebar_collapsed: false,
  revision: 0,
}
const SAVED: UserPreferences = {
  locale: 'de',
  theme: 'light',
  desktop_sidebar_collapsed: false,
  revision: 7,
}
const wrappers: VueWrapper[] = []

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function failure(status = 503, code = 'internal_error'): Response {
  return jsonResponse(
    { error: { code, message: 'Private server error text must not be displayed.' } },
    status,
  )
}

function deferredResponse() {
  let resolve: (value: Response) => void = () => {
    throw new Error('The response promise must be initialized before resolving it.')
  }
  const promise = new Promise<Response>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

async function mountSettings(
  locale: AppLocale,
  handler: (request: Request) => Response | Promise<Response>,
  isReady = true,
) {
  const pinia = createPinia()
  const queryClient = createQueryClient()
  const router = createAppRouter(createMemoryHistory())
  await router.push('/settings')
  await router.isReady()
  const client = createApiClient({ fetch: (request) => Promise.resolve(handler(request)) })
  const wrapper = mount(UserSettingsView, {
    attachTo: document.body,
    global: {
      plugins: [pinia, createAppI18n(locale), router, [VueQueryPlugin, { queryClient }]],
      provide: { [API_CLIENT_KEY as symbol]: client },
    },
  })
  wrappers.push(wrapper)
  const session = useSessionStore(pinia)
  if (isReady) {
    session.user = USER_A
    session.status = 'ready'
  }
  await flushPromises()
  return { wrapper, session, queryClient, router }
}

function selectByLabel(wrapper: VueWrapper, text: string) {
  const label = wrapper.findAll('label').find((candidate) => candidate.text() === text)
  if (!label) throw new Error(`No field labelled ${text}.`)
  return wrapper.get<HTMLSelectElement>(`#${label.attributes('for')}`)
}

function buttonWithText(wrapper: VueWrapper, text: string): DOMWrapper<HTMLButtonElement> {
  const button = wrapper
    .findAll<HTMLButtonElement>('button')
    .find((candidate) => candidate.text() === text)
  if (!button) throw new Error(`No button labelled ${text}.`)
  return button
}

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  document.body.replaceChildren()
  document.documentElement.removeAttribute('data-theme')
})

describe.each(['de', 'en'] as const)('personal settings in %s', (locale) => {
  const messages = catalogues[locale].userSettings

  it('waits for preferences and renders virtual defaults for an account with no roles', async () => {
    const response = deferredResponse()
    const { wrapper } = await mountSettings(locale, () => response.promise)
    expect(wrapper.get('[role="status"]').text()).toBe(messages.loading)
    expect(wrapper.find('form').exists()).toBe(false)

    response.resolve(jsonResponse(DEFAULTS))
    await waitFor(() => expect(wrapper.find('form').exists()).toBe(true))
    expect(selectByLabel(wrapper, messages.language.label).element.selectedOptions[0]?.text).toBe(
      messages.language.browserDefault,
    )
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('system')
    expect(selectByLabel(wrapper, messages.sidebar.label).element.selectedOptions[0]?.text).toBe(
      messages.sidebar.expanded,
    )
    expect(buttonWithText(wrapper, messages.save).element.disabled).toBe(true)
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unchanged)
  })

  it('keeps drafts local, saves with the loaded revision and adopts the canonical response', async () => {
    const response = deferredResponse()
    const bodies: unknown[] = []
    const { wrapper, queryClient } = await mountSettings(locale, async (request) => {
      if (request.method === 'GET') return jsonResponse(SAVED)
      bodies.push(await request.json())
      return response.promise
    })
    const liveRegion = wrapper.get('[role="status"]').element
    await selectByLabel(wrapper, messages.theme.label).setValue('dark')
    await selectByLabel(wrapper, messages.sidebar.label).setValue('true')
    expect(bodies).toHaveLength(0)
    expect(queryClient.getQueriesData({ type: 'active' }).map(([, data]) => data)).toEqual([SAVED])
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unsaved)

    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({
      locale: 'de',
      theme: 'dark',
      desktop_sidebar_collapsed: true,
      expected_revision: 7,
    })
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.saving)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(buttonWithText(wrapper, messages.save).element.disabled).toBe(true)
    const canonical = {
      ...SAVED,
      theme: 'dark',
      desktop_sidebar_collapsed: true,
      revision: 8,
    } as const
    response.resolve(jsonResponse(canonical))
    await waitFor(() => expect(wrapper.get('[role="status"]').text()).toBe(messages.states.saved))
    expect(wrapper.get('[role="status"]').element).toBe(liveRegion)
    expect(queryClient.getQueriesData({ type: 'active' }).map(([, data]) => data)).toEqual([
      canonical,
    ])
    await selectByLabel(wrapper, messages.theme.label).setValue('light')
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies[1]).toMatchObject({ expected_revision: 8 })
  })

  it('restores defaults only in the draft and explicitly clears locale when saved', async () => {
    const bodies: unknown[] = []
    const { wrapper, queryClient } = await mountSettings(locale, async (request) => {
      if (request.method === 'GET')
        return jsonResponse({ ...SAVED, desktop_sidebar_collapsed: true })
      bodies.push(await request.json())
      return jsonResponse({ ...DEFAULTS, revision: 8 })
    })
    await buttonWithText(wrapper, messages.restoreDefaults).trigger('click')
    expect(bodies).toHaveLength(0)
    expect(queryClient.getQueriesData({ type: 'active' }).map(([, data]) => data)).toMatchObject([
      { locale: 'de' },
    ])
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unsaved)
    await wrapper.get('form').trigger('submit')
    await waitFor(() =>
      expect(bodies).toEqual([
        { locale: null, theme: 'system', desktop_sidebar_collapsed: false, expected_revision: 7 },
      ]),
    )
  })

  it('keeps native null and false choices through failed save and explicit retry', async () => {
    let fails = true
    const bodies: unknown[] = []
    const canonical = { ...SAVED, locale: null, desktop_sidebar_collapsed: false, revision: 8 }
    const { wrapper, queryClient } = await mountSettings(locale, async (request) => {
      if (request.method === 'GET') {
        return jsonResponse({ ...SAVED, desktop_sidebar_collapsed: true })
      }
      bodies.push(await request.json())
      return fails ? failure() : jsonResponse(canonical)
    })
    const language = selectByLabel(wrapper, messages.language.label)
    const browserDefault = language
      .findAll('option')
      .find((option) => option.text() === messages.language.browserDefault)
    const sidebar = selectByLabel(wrapper, messages.sidebar.label)
    const expanded = sidebar
      .findAll('option')
      .find((option) => option.text() === messages.sidebar.expanded)
    if (!browserDefault || !expanded) throw new Error('Native settings choices are missing.')
    await language.setValue(browserDefault.element.value)
    await sidebar.setValue(expanded.element.value)
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(wrapper.find('[role="alert"]').exists()).toBe(true))
    expect(language.element.value).toBe(browserDefault.element.value)
    expect(sidebar.element.value).toBe(expanded.element.value)
    expect(bodies[0]).toEqual({
      locale: null,
      theme: SAVED.theme,
      desktop_sidebar_collapsed: false,
      expected_revision: SAVED.revision,
    })
    fails = false
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(wrapper.find('[role="status"]').exists()).toBe(true))
    expect(bodies).toEqual([bodies[0], bodies[0]])
    expect(queryClient.getQueriesData({ type: 'active' }).map(([, data]) => data)).toEqual([
      canonical,
    ])
  })

  it('shows a read error and retries without pretending default values were loaded', async () => {
    let fails = true
    const { wrapper } = await mountSettings(locale, () =>
      fails ? failure() : jsonResponse(DEFAULTS),
    )
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.loadError))
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Private server error text')
    fails = false
    await buttonWithText(wrapper, messages.retry).trigger('click')
    await waitFor(() => expect(wrapper.find('form').exists()).toBe(true))
    expect(wrapper.get('[role="alert"]').text()).toBe('')
  })

  it.each(['server', 'network'] as const)(
    'retains a failed %s save and lets the user retry',
    async (kind) => {
      let fails = true
      const bodies: unknown[] = []
      const { wrapper } = await mountSettings(locale, async (request) => {
        if (request.method === 'GET') return jsonResponse(SAVED)
        bodies.push(await request.json())
        if (fails && kind === 'network') throw new TypeError('Network unavailable')
        if (fails) return failure()
        return jsonResponse({ ...SAVED, theme: 'dark', revision: 8 })
      })
      await selectByLabel(wrapper, messages.theme.label).setValue('dark')
      await wrapper.get('form').trigger('submit')
      await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.saveError))
      expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('dark')
      expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unsaved)
      expect(buttonWithText(wrapper, messages.save).element.disabled).toBe(false)
      fails = false
      await wrapper.get('form').trigger('submit')
      await waitFor(() => expect(wrapper.get('[role="status"]').text()).toBe(messages.states.saved))
      expect(bodies).toHaveLength(2)
      expect(bodies[0]).toEqual(bodies[1])
    },
  )

  it('blocks a conflicting save until a deliberate successful reload replaces the draft', async () => {
    let reads = 0
    let writes = 0
    let reloadFails = true
    const latest = { ...SAVED, theme: 'system', revision: 9 } as const
    const { wrapper } = await mountSettings(locale, (request) => {
      if (request.method === 'PATCH') {
        writes += 1
        return failure(409, 'preferences_revision_conflict')
      }
      reads += 1
      if (reads === 1) return jsonResponse(SAVED)
      return reloadFails ? failure() : jsonResponse(latest)
    })
    await selectByLabel(wrapper, messages.theme.label).setValue('dark')
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.conflict))
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('dark')
    expect(buttonWithText(wrapper, messages.save).element.disabled).toBe(true)
    await wrapper.get('form').trigger('submit')
    expect(writes).toBe(1)
    expect(reads).toBe(1)
    await buttonWithText(wrapper, messages.reloadSaved).trigger('click')
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.reloadError))
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('dark')
    expect(buttonWithText(wrapper, messages.save).element.disabled).toBe(true)

    reloadFails = false
    await buttonWithText(wrapper, messages.reloadSaved).trigger('click')
    await waitFor(() =>
      expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('system'),
    )
    expect(wrapper.get('[role="alert"]').text()).toBe('')
    expect(wrapper.text()).not.toContain(messages.conflictReloadHint)
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unchanged)
  })

  it('preserves a dirty draft and its revision across background refetches', async () => {
    const bodies: unknown[] = []
    let saved = SAVED
    const { wrapper, queryClient } = await mountSettings(locale, async (request) => {
      if (request.method === 'GET') return jsonResponse(saved)
      bodies.push(await request.json())
      return failure(409, 'preferences_revision_conflict')
    })
    await selectByLabel(wrapper, messages.theme.label).setValue('dark')
    saved = { ...SAVED, theme: 'system', revision: 8 }
    await queryClient.invalidateQueries({ type: 'active' })
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('dark')
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toMatchObject({ expected_revision: 7 })
  })

  it('retries a background read error without replacing a dirty draft or its revision', async () => {
    let readFails = false
    const bodies: unknown[] = []
    const { wrapper, queryClient } = await mountSettings(locale, async (request) => {
      if (request.method === 'PATCH') {
        bodies.push(await request.json())
        return failure(409, 'preferences_revision_conflict')
      }
      return readFails ? failure() : jsonResponse(SAVED)
    })
    await selectByLabel(wrapper, messages.theme.label).setValue('dark')
    readFails = true
    await queryClient.invalidateQueries({ type: 'active' })
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.loadError))
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('dark')
    readFails = false
    await buttonWithText(wrapper, messages.retry).trigger('click')
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(''))
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('dark')
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unsaved)
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toMatchObject({ theme: 'dark', expected_revision: 7 })
  })

  it('clears a previous reload error after a confirmed successful save', async () => {
    let reads = 0
    const { wrapper, queryClient } = await mountSettings(locale, (request) => {
      if (request.method === 'PATCH') return jsonResponse({ ...SAVED, theme: 'dark', revision: 8 })
      reads += 1
      return reads === 1 ? jsonResponse(SAVED) : failure()
    })
    await selectByLabel(wrapper, messages.theme.label).setValue('dark')
    await queryClient.invalidateQueries({ type: 'active' })
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.loadError))
    await buttonWithText(wrapper, messages.retry).trigger('click')
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.reloadError))
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('dark')
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(wrapper.get('[role="status"]').text()).toBe(messages.states.saved))
    expect(wrapper.get('[role="alert"]').text()).toBe('')
    expect(buttonWithText(wrapper, messages.save).element.disabled).toBe(true)
  })

  it('discards an old account’s draft and ignores its late save response', async () => {
    const response = deferredResponse()
    let reads = 0
    const { wrapper, session, queryClient } = await mountSettings(locale, (request) => {
      if (request.method === 'PATCH') return response.promise
      reads += 1
      return jsonResponse(reads === 1 ? SAVED : DEFAULTS)
    })
    const oldAccountQueries = queryClient.getQueryCache().findAll({ type: 'active' })
    await selectByLabel(wrapper, messages.theme.label).setValue('dark')
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(wrapper.get('[role="status"]').text()).toBe(messages.states.saving))
    session.user = USER_B
    await waitFor(() =>
      expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('system'),
    )
    response.resolve(jsonResponse({ ...SAVED, theme: 'dark', revision: 8 }))
    await flushPromises()
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('system')
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unchanged)
    for (const query of oldAccountQueries) {
      expect(queryClient.getQueryCache().getAll()).not.toContain(query)
    }
    expect(queryClient.getQueriesData({ type: 'active' }).map(([, data]) => data)).toEqual([
      DEFAULTS,
    ])
  })

  it('ignores a late initial read after switching accounts', async () => {
    const response = deferredResponse()
    let reads = 0
    const { wrapper, session } = await mountSettings(locale, () => {
      reads += 1
      return reads === 1 ? response.promise : jsonResponse(DEFAULTS)
    })
    session.user = USER_B
    await waitFor(() => expect(wrapper.find('form').exists()).toBe(true))
    response.resolve(jsonResponse({ ...SAVED, theme: 'dark' }))
    await flushPromises()
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('system')
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unchanged)
  })

  it('ignores a conflict reload completed for a previous account', async () => {
    const response = deferredResponse()
    let reads = 0
    const { wrapper, session } = await mountSettings(locale, (request) => {
      if (request.method === 'PATCH') return failure(409, 'preferences_revision_conflict')
      reads += 1
      if (reads === 1) return jsonResponse(SAVED)
      if (reads === 2) return response.promise
      return jsonResponse(DEFAULTS)
    })
    await selectByLabel(wrapper, messages.theme.label).setValue('dark')
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.conflict))
    await buttonWithText(wrapper, messages.reloadSaved).trigger('click')
    await waitFor(() => expect(reads).toBe(2))
    session.user = USER_B
    await waitFor(() =>
      expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('system'),
    )
    response.resolve(jsonResponse({ ...SAVED, theme: 'dark', revision: 8 }))
    await flushPromises()
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('system')
    expect(wrapper.get('[role="alert"]').text()).toBe('')
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unchanged)
  })

  it('hides but preserves the draft while the same account authenticates again', async () => {
    const { wrapper, session } = await mountSettings(locale, () => jsonResponse(SAVED))
    await selectByLabel(wrapper, messages.theme.label).setValue('dark')
    session.isAuthenticating = true
    await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    session.isAuthenticating = false
    await waitFor(() => expect(wrapper.find('form').exists()).toBe(true))
    expect(selectByLabel(wrapper, messages.theme.label).element.value).toBe('dark')
    expect(wrapper.get('[role="status"]').text()).toBe(messages.states.unsaved)
  })

  it.each(['signedOut', 'passwordChangeRequired'] as const)(
    'redirects %s access without fetching preferences',
    async (access) => {
      let reads = 0
      const { wrapper, session, router } = await mountSettings(
        locale,
        () => {
          reads += 1
          return jsonResponse(DEFAULTS)
        },
        false,
      )
      if (access === 'passwordChangeRequired') {
        session.user = USER_A
        session.mustChangePassword = true
      }
      session.status = 'ready'
      await waitFor(() =>
        expect(router.currentRoute.value.name).toBe(
          access === 'signedOut' ? 'login' : 'changePassword',
        ),
      )
      expect(router.currentRoute.value.query.redirect).toBe('/settings')
      expect(reads).toBe(0)
      expect(wrapper.find('form').exists()).toBe(false)
    },
  )

  it('reports a session load failure and retries session resolution', async () => {
    const { wrapper, session } = await mountSettings(
      locale,
      (request) => {
        const path = new URL(request.url).pathname
        if (path === '/api/v1/me') return jsonResponse(USER_A)
        if (path === '/api/v1/auth/session')
          return jsonResponse({ must_change_password: false, keep_signed_in: false })
        return jsonResponse(DEFAULTS)
      },
      false,
    )
    expect(wrapper.get('[role="status"]').text()).toBe(messages.loadingAccess)
    session.status = 'error'
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe(messages.sessionLoadError)
    await buttonWithText(wrapper, messages.retry).trigger('click')
    await waitFor(() => expect(wrapper.find('form').exists()).toBe(true))
  })

  it('redirects a password restriction returned by a save and hides the private draft', async () => {
    const { wrapper, router } = await mountSettings(locale, (request) =>
      request.method === 'GET' ? jsonResponse(SAVED) : failure(403, 'password_change_required'),
    )
    await selectByLabel(wrapper, messages.theme.label).setValue('dark')
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(router.currentRoute.value.name).toBe('changePassword'))
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it.each(['light', 'dark'] as const)(
    'has labelled keyboard-focusable native controls and no axe violations in %s theme',
    async (theme) => {
      document.documentElement.dataset.theme = theme
      const { wrapper } = await mountSettings(locale, () => jsonResponse(SAVED))
      for (const label of [messages.language.label, messages.theme.label, messages.sidebar.label]) {
        const select = selectByLabel(wrapper, label)
        select.element.focus()
        expect(document.activeElement).toBe(select.element)
        expect(select.attributes('aria-describedby')).toBeTruthy()
      }
      await selectByLabel(wrapper, messages.theme.label).setValue('dark')
      const save = buttonWithText(wrapper, messages.save)
      save.element.focus()
      expect(document.activeElement).toBe(save.element)
      expect(save.attributes('type')).toBe('submit')
      await expectNoAxeViolations(wrapper.element)
    },
  )
})
