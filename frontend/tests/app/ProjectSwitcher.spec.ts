import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const PROJECT_A = 'b0000000-0000-0000-0000-000000000001'
const PROJECT_B = 'b0000000-0000-0000-0000-000000000002'
const project = (id: string, name: string) => ({
  id,
  slug: name.toLowerCase().replace(' ', '-'),
  display_name: name,
  current_user_role: 'operator',
  created_at: '2026-01-01T00:00:00Z',
})
const ROUTES: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': { body: USER },
  '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
  '/api/v1/projects': {
    body: {
      items: [project(PROJECT_A, 'Project A'), project(PROJECT_B, 'Project B')],
      has_more: false,
      next_cursor: null,
    },
  },
  [`/api/v1/projects/${PROJECT_A}`]: { body: project(PROJECT_A, 'Project A') },
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('ProjectSwitcher in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projectSwitcher

  it('is not offered without a session', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': {
          body: { error: { code: 'authentication_required', message: 'No session.' } },
          init: { status: 401 },
        },
      }),
    )
    await flushPromises()

    expect(wrapper.find('header button[aria-haspopup="menu"]').exists()).toBe(false)
  })

  it('asks for a project outside one', async () => {
    const wrapper = await mountApplicationAt('/projects', locale, apiClientWithRoutes(ROUTES))

    await waitFor(() => {
      expect(wrapper.get('header button[aria-haspopup="menu"]').text()).toBe(messages.choose)
    })
  })

  it('names the current project, lists the projects and marks the current one', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes(ROUTES),
    )
    await waitFor(() => {
      expect(wrapper.get('header button[aria-haspopup="menu"]').text()).toBe('Project A')
    })

    await wrapper.get('header button[aria-haspopup="menu"]').trigger('click')
    await waitFor(() => expect(wrapper.find('header [role="menuitem"]').exists()).toBe(true))

    const items = wrapper.findAll('header [role="menuitem"]')
    expect(items.map((item) => item.text())).toEqual(['Project A', 'Project B', messages.all])
    expect(items[0]?.attributes('aria-current')).toBe('true')
    expect(items[1]?.attributes('href')).toBe(`/projects/${PROJECT_B}/overview`)
    expect(items[2]?.attributes('href')).toBe('/projects')
  })

  it('says so when the projects cannot be loaded', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
      locale,
      apiClientWithRoutes({
        ...ROUTES,
        '/api/v1/projects': { body: { error: { code: 'x', message: 'x' } }, init: { status: 500 } },
      }),
    )
    await waitFor(() =>
      expect(wrapper.find('header button[aria-haspopup="menu"]').exists()).toBe(true),
    )
    await wrapper.get('header button[aria-haspopup="menu"]').trigger('click')

    await waitFor(() => {
      expect(wrapper.get('header [role="alert"]').text()).toBe(messages.loadError)
    })
  })
})
