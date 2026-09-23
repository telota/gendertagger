import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const NOT_SIGNED_IN: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': {
    body: { error: { code: 'authentication_required', message: 'Authentication is required.' } },
    init: { status: 401 },
  },
}
const SIGNED_IN: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': { body: USER },
  '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
  '/api/v1/projects': { body: { items: [], has_more: false, next_cursor: null } },
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('AppSidebar in %s', (locale: AppLocale) => {
  it('always links the brand to the start page', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))

    const brand = wrapper.get('aside a[href="/"]')
    expect(brand.text()).toBe(catalogues[locale].app.title)
  })

  it('offers one navigation item for the project list', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))

    const projectsLink = wrapper.get('aside a[href="/projects"]')
    expect(projectsLink.text()).toBe(catalogues[locale].nav.projects)
  })

  it('marks the current location on the matching navigation item', async () => {
    const wrapper = await mountApplicationAt('/projects', locale, apiClientWithRoutes(SIGNED_IN))

    // /projects is lazy; its first import in this test file's process needs more than one
    // macrotask tick to resolve. See tests/helpers/wait.ts.
    await waitFor(() => {
      expect(wrapper.get('aside a[href="/projects"]').attributes('aria-current')).toBe('page')
    })
  })
})
