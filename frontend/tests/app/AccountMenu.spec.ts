import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { createApiClient, type ApiClient } from '@/api'
import AccountMenu from '@/app/AccountMenu.vue'
import { createAppI18n, type AppLocale } from '@/app/i18n'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { useSessionRecovery } from '@/composables/useSessionRecovery'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore } from '@/stores/session'

import { apiClientWithRoutes } from '../helpers/api'
import { expectNoAxeViolations } from '../helpers/axe'
import { waitFor } from '../helpers/wait'

const drafts = vi.hoisted(() => ({ confirmLeave: vi.fn(), discardDrafts: vi.fn() }))
vi.mock('@/composables/useDraftNavigation', () => ({ useDraftNavigation: () => drafts }))

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const catalogues = { de, en } as const
const EmptyPage = defineComponent({ template: '<main />' })
const wrappers: ReturnType<typeof mount>[] = []

async function mountMenu(locale: AppLocale, client: ApiClient = apiClientWithRoutes({})) {
  const pinia = createPinia()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: EmptyPage },
      { path: '/projects', name: 'projects', component: EmptyPage },
      { path: '/settings', name: 'userSettings', component: EmptyPage },
      { path: '/login', name: 'login', component: EmptyPage },
    ],
  })
  await router.push('/projects')
  const wrapper = mount(AccountMenu, {
    attachTo: document.body,
    global: {
      plugins: [pinia, createAppI18n(locale), router],
      provide: { [API_CLIENT_KEY as symbol]: client },
    },
  })
  wrappers.push(wrapper)
  const session = useSessionStore(pinia)
  session.user = USER
  session.status = 'ready'
  await flushPromises()
  return { wrapper, session, router }
}

beforeEach(() => {
  drafts.confirmLeave.mockResolvedValue(true)
  drafts.discardDrafts.mockClear()
})

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  useSessionRecovery().reject(new Error('Test cleanup'))
  vi.clearAllMocks()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('AccountMenu in %s', (locale) => {
  const messages = catalogues[locale].header

  it('shows the full account name, exposes settings and sign out, and supports Escape', async () => {
    const { wrapper } = await mountMenu(locale)
    const button = wrapper.get<HTMLButtonElement>('.account-menu-button')
    expect(button.text()).toBe(USER.display_name)
    expect(button.attributes('aria-label')).toBe(
      messages.accountMenu.replace('{name}', USER.display_name),
    )
    button.element.focus()
    await button.trigger('keydown', { key: 'ArrowDown' })
    await waitFor(() => expect(wrapper.find('[role="menu"]').exists()).toBe(true))
    expect(wrapper.findAll('[role="menuitem"]').map((item) => item.text())).toEqual([
      messages.settings,
      messages.signOut,
    ])
    expect(wrapper.get('a[role="menuitem"]').attributes('href')).toBe('/settings')
    await expectNoAxeViolations(wrapper.element)

    await wrapper.get('[role="menu"]').trigger('keydown', { key: 'Escape' })
    await waitFor(() => expect(wrapper.find('[role="menu"]').exists()).toBe(false))
    await waitFor(() => expect(document.activeElement).toBe(button.element))
  })

  it('keeps sign out available when a password change is required', async () => {
    const { wrapper, session } = await mountMenu(locale)
    session.mustChangePassword = true
    await flushPromises()
    await wrapper.get('.account-menu-button').trigger('click')

    expect(wrapper.find('a[href="/settings"]').exists()).toBe(false)
    expect(wrapper.get('[role="menuitem"]').text()).toBe(messages.signOut)
  })

  it('closes stale menus when the principal changes or recovery starts', async () => {
    const { wrapper, session } = await mountMenu(locale)
    await wrapper.get('.account-menu-button').trigger('click')
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)
    session.user = { ...USER, id: 'other-user', display_name: 'Other Reviewer' }
    await flushPromises()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(wrapper.get('.account-menu-button').text()).toBe('Other Reviewer')

    await wrapper.get('.account-menu-button').trigger('click')
    useSessionRecovery().isOpen.value = true
    await flushPromises()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(wrapper.get<HTMLButtonElement>('.account-menu-button').element.disabled).toBe(true)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('cancels sign-out without calling the API or abandoning drafts', async () => {
    const fetch = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })))
    const { wrapper, session, router } = await mountMenu(locale, createApiClient({ fetch }))
    drafts.confirmLeave.mockResolvedValue(false)
    await wrapper.get('.account-menu-button').trigger('click')
    await wrapper.get('button[role="menuitem"]').trigger('click')
    await flushPromises()

    expect(fetch).not.toHaveBeenCalled()
    expect(drafts.discardDrafts).not.toHaveBeenCalled()
    expect(session.user).toEqual(USER)
    expect(router.currentRoute.value.name).toBe('projects')
  })

  it('preserves account and draft state on failure, then permits an explicit retry', async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('fetch failed'))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    const { wrapper, session, router } = await mountMenu(locale, createApiClient({ fetch }))
    await wrapper.get('.account-menu-button').trigger('click')
    await wrapper.get('button[role="menuitem"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(messages.signOutError)
    expect(session.user).toEqual(USER)
    expect(drafts.discardDrafts).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('projects')
    await expectNoAxeViolations(wrapper.element)

    await wrapper.get('.account-menu-retry').trigger('click')
    await flushPromises()
    expect(drafts.confirmLeave).toHaveBeenCalledTimes(2)
    expect(drafts.discardDrafts).toHaveBeenCalledOnce()
    expect(session.user).toBeNull()
    expect(router.currentRoute.value.name).toBe('home')
    expect(wrapper.find('.account-menu').exists()).toBe(false)
  })

  it.each([204, 500])(
    'ignores a late HTTP %s logout outcome owned by the previous account',
    async (status) => {
      let resolveLogout!: (response: Response) => void
      const pending = new Promise<Response>((resolve) => {
        resolveLogout = resolve
      })
      const { wrapper, session, router } = await mountMenu(
        locale,
        createApiClient({ fetch: () => pending }),
      )
      await wrapper.get('.account-menu-button').trigger('click')
      await wrapper.get('button[role="menuitem"]').trigger('click')
      await flushPromises()
      session.user = { ...USER, id: 'other-user', display_name: 'Other Reviewer' }
      await flushPromises()
      resolveLogout(
        status === 204
          ? new Response(null, { status })
          : Response.json(
              { error: { code: 'internal_error', message: 'Unavailable.' } },
              { status },
            ),
      )
      await flushPromises()

      expect(session.user?.id).toBe('other-user')
      expect(drafts.discardDrafts).not.toHaveBeenCalled()
      expect(router.currentRoute.value.name).toBe('projects')
      expect(wrapper.find('[role="alert"]').exists()).toBe(false)
      expect(wrapper.get('.account-menu-button').text()).toBe('Other Reviewer')
      expect(wrapper.get<HTMLButtonElement>('.account-menu-button').element.disabled).toBe(false)
    },
  )

  it('disables repeat requests while signing out', async () => {
    let resolve!: (response: Response) => void
    const pending = new Promise<Response>((settle) => {
      resolve = settle
    })
    const fetch = vi.fn(() => pending)
    const { wrapper, router } = await mountMenu(locale, createApiClient({ fetch }))
    await router.push('/')
    await wrapper.get('.account-menu-button').trigger('click')
    await wrapper.get('button[role="menuitem"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe(messages.signingOut)
    expect(wrapper.get<HTMLButtonElement>('.account-menu-button').element.disabled).toBe(true)
    expect(fetch).toHaveBeenCalledOnce()

    resolve(new Response(null, { status: 204 }))
    await flushPromises()
    expect(wrapper.find('.account-menu').exists()).toBe(false)
  })

  it('distinguishes checking, failed session checks, and signed-out state', async () => {
    const { wrapper, session, router } = await mountMenu(
      locale,
      apiClientWithRoutes({
        '/api/v1/me': {
          body: { error: { code: 'authentication_required', message: 'Gone.' } },
          init: { status: 401 },
        },
      }),
    )
    await router.push('/')
    session.status = 'loading'
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe(messages.loading)
    expect(wrapper.find('a[href="/login"]').exists()).toBe(false)
    session.status = 'error'
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe(messages.serverError)
    expect(wrapper.find('a[href="/login"]').exists()).toBe(false)

    await wrapper.get('.account-menu-retry').trigger('click')
    await flushPromises()
    expect(wrapper.find('.account-menu').exists()).toBe(false)

    await router.push('/login')
    expect(wrapper.get('a[href="/login"]').text()).toBe(messages.signIn)
    await router.push('/')
    expect(wrapper.find('.account-menu').exists()).toBe(false)
  })
})
