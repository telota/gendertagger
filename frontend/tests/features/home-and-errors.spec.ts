import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithJsonResponse, apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { expectNoAxeViolations } from '../helpers/axe'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const PROJECT = {
  id: 'b0000000-0000-0000-0000-000000000001',
  display_name: 'Women Writers Register',
  slug: 'women-writers',
  description: 'Editorial review of the edition person register.',
  created_at: '2026-09-01T12:00:00Z',
  created_by_user_id: 'a0000000-0000-0000-0000-000000000002',
  manager_user_id: 'a0000000-0000-0000-0000-000000000002',
  current_user_can_manage_members: false,
  current_user_role: 'reviewer',
  working_aggregation_execution_id: null,
  team: {
    id: 'c0000000-0000-0000-0000-000000000001',
    display_name: 'Edition team',
    slug: 'edition-team',
    created_at: '2026-08-01T12:00:00Z',
    updated_at: '2026-08-01T12:00:00Z',
  },
}
const PROJECT_PAGE = { items: [PROJECT], has_more: false, next_cursor: null }
const SIGNED_OUT_ROUTES: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': {
    body: { error: { code: 'authentication_required', message: 'Authentication is required.' } },
    init: { status: 401 },
  },
}

/** Fill in and submit the sign-in form of the signed-out home page. */
async function signInFromHome(
  wrapper: Awaited<ReturnType<typeof mountApplicationAt>>,
  password: string,
): Promise<void> {
  await wrapper.get('main input[name="username"]').setValue('reviewer.one')
  await wrapper.get('main input[name="password"]').setValue(password)
  await wrapper.get('main form').trigger('submit')
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('home page in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].home

  it('greets a signed-out visitor with the guest introduction and an inline sign-in form', async () => {
    const page = (await mountApplicationAt('/', locale, apiClientWithJsonResponse({}))).get('main')

    expect(page.get('h1').text()).toBe(messages.guest.lede)
    expect(page.find('a[href="/login"]').exists()).toBe(false)
    expect(page.get('form').attributes('aria-label')).toBe(catalogues[locale].login.title)
    expect(page.get('input[name="username"]').attributes('autocomplete')).toBe('username')
    expect(page.get('input[name="password"]').attributes('type')).toBe('password')
    expect(page.find('input[type="checkbox"]').exists()).toBe(true)
    expect(page.get('button[type="submit"]').text()).toBe(catalogues[locale].login.submit)
    expect(page.text()).toContain(messages.guest.accountHint)
    expect(page.findAll('ol > li')).toHaveLength(3)
  })

  it('offers a sign-in form without axe violations, also after a failed attempt', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        ...SIGNED_OUT_ROUTES,
        '/api/v1/auth/login': {
          body: { error: { code: 'invalid_credentials', message: 'Wrong.' } },
          init: { status: 401 },
        },
      }),
    )
    await expectNoAxeViolations(wrapper.element)

    await signInFromHome(wrapper, 'wrong')
    await flushPromises()
    await expectNoAxeViolations(wrapper.element)
  })

  it('signs in from the home page and continues to the signed-in dashboard there (D26)', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        ...SIGNED_OUT_ROUTES,
        '/api/v1/auth/login': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
      }),
    )

    await signInFromHome(wrapper, 'a-correct-passphrase')

    await waitFor(() => expect(wrapper.vm.$route.fullPath).toBe('/'))
    expect(wrapper.get('header').text()).toContain('Reviewer One')
  })

  it('continues to the forced password change when the session requires it', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        ...SIGNED_OUT_ROUTES,
        '/api/v1/auth/login': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: true, keep_signed_in: false } },
      }),
    )

    await signInFromHome(wrapper, 'a-correct-passphrase')

    await waitFor(() => {
      expect(wrapper.get('main h1').text()).toBe(catalogues[locale].changePassword.title)
    })
    expect(wrapper.vm.$route.query.redirect).toBe('/')
  })

  it('shows wrong credentials inline and stays on the home page', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        ...SIGNED_OUT_ROUTES,
        '/api/v1/auth/login': {
          body: { error: { code: 'invalid_credentials', message: 'Wrong.' } },
          init: { status: 401 },
        },
      }),
    )

    await signInFromHome(wrapper, 'wrong')
    await flushPromises()

    expect(wrapper.get('main [role="alert"]').text()).toBe(
      catalogues[locale].login.errors.invalidCredentials,
    )
    expect(wrapper.vm.$route.fullPath).toBe('/')
  })

  it('shows a personalized project dashboard to a signed-in visitor', async () => {
    const user = {
      id: 'a0000000-0000-0000-0000-000000000009',
      display_name: 'Ada Lovelace',
      roles: [] as string[],
    }
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': { body: user },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
        '/api/v1/projects': { body: PROJECT_PAGE },
      }),
    )
    const page = wrapper.get('main')
    await waitFor(() => expect(page.findAll('.home-project-row')).toHaveLength(1))

    expect(page.get('h1').text()).toBe(
      messages.signedIn.welcomeBack.replace('{name}', user.display_name),
    )
    expect(page.text()).toContain(messages.signedIn.introduction)
    expect(page.text()).toContain(PROJECT.display_name)
    expect(page.text()).toContain(PROJECT.team.display_name)
    expect(page.text()).toContain(catalogues[locale].projects.role.reviewer)
    expect(page.get('.home-project-panel').classes()).toEqual(
      expect.arrayContaining(['app-card', 'app-card--sectioned']),
    )
    expect(page.findAll(`a[href="/projects/${PROJECT.id}/overview"]`)).toHaveLength(2)
    expect(page.get('a[href="/settings"]').text()).toBe(
      messages.signedIn.workspace.personalSettings,
    )
    expect(page.text()).toContain(messages.signedIn.workspace.access.projectAccessDescription)
    expect(page.find('a[href="/admin/users"]').exists()).toBe(false)
    await expectNoAxeViolations(wrapper.element)
  })

  it('does not infer project membership when an account has no project access', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
        '/api/v1/projects': { body: { items: [], has_more: false, next_cursor: null } },
      }),
    )
    const page = wrapper.get('main')
    await waitFor(() => expect(page.text()).toContain(catalogues[locale].projects.empty))

    expect(page.text()).toContain(catalogues[locale].projects.emptyHint)
    expect(page.text()).toContain(messages.signedIn.workspace.access.projectAccess)
    expect(page.text()).toContain(messages.signedIn.workspace.access.projectAccessDescription)
  })

  it('adapts workspace shortcuts and the empty state to an administrator', async () => {
    const administrator = {
      id: 'a0000000-0000-0000-0000-000000000010',
      display_name: 'Admin User',
      roles: ['admin'],
    }
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': { body: administrator },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
        '/api/v1/projects': { body: { items: [], has_more: false, next_cursor: null } },
      }),
    )
    const page = wrapper.get('main')
    await waitFor(() => expect(page.text()).toContain(catalogues[locale].projects.empty))

    expect(page.text()).toContain(catalogues[locale].projects.emptyCreateHint)
    expect(page.text()).toContain(messages.signedIn.workspace.access.adminDescription)
    expect(page.find('a[href="/admin/users"]').exists()).toBe(true)
    expect(page.find('a[href="/admin/teams"]').exists()).toBe(true)
    expect(page.find('a[href="/admin/settings"]').exists()).toBe(true)
    await expectNoAxeViolations(wrapper.element)
  })

  it('keeps project loading failure recoverable on the dashboard', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
        '/api/v1/projects': {
          body: { error: { code: 'internal_error', message: 'Unavailable.' } },
          init: { status: 500 },
        },
      }),
    )
    const page = wrapper.get('main')
    await waitFor(() =>
      expect(page.get('[role="alert"]').text()).toContain(catalogues[locale].projects.loadError),
    )

    expect(
      page.findAll('button').some((button) => button.text() === catalogues[locale].projects.retry),
    ).toBe(true)
  })
})

describe.each(['de', 'en'] as const)('page not found in %s', (locale: AppLocale) => {
  it('explains the miss and links back to the start page', async () => {
    const client = apiClientWithJsonResponse({})
    const page = (await mountApplicationAt('/gibt-es-nicht', locale, client)).get('main')
    const messages = catalogues[locale].notFound

    expect(page.get('h1').text()).toBe(messages.title)
    expect(page.get('a[href="/"]').text()).toBe(messages.backToStart)
  })
})
