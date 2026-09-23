import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../../helpers/api'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const

const VIEWER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Viewer One', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const PROJECT = {
  id: PROJECT_ID,
  slug: 'project-a',
  display_name: 'Project A',
  description: 'The first project.',
  current_user_role: 'viewer',
  created_at: '2026-01-01T00:00:00Z',
}

function signedInRoutes(projectBody: RouteResponse): Record<string, RouteResponse> {
  return {
    '/api/v1/branding': { body: {} },
    '/api/v1/me': { body: VIEWER },
    '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    [`/api/v1/projects/${PROJECT_ID}`]: projectBody,
  }
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('ProjectOverviewView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projects

  it('shows the project name, slug, role, and description', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(signedInRoutes({ body: PROJECT })),
    )
    await flushPromises()

    expect(wrapper.get('main h1').text()).toBe('Project A')
    expect(wrapper.text()).toContain(PROJECT.slug)
    expect(wrapper.text()).toContain(messages.role.viewer)
    expect(wrapper.text()).toContain('The first project.')
  })

  it('shows a placeholder when the project has no description', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(signedInRoutes({ body: { ...PROJECT, description: null } })),
    )
    await flushPromises()

    expect(wrapper.text()).toContain(messages.overview.noDescription)
  })

  it('links to the import screen', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(signedInRoutes({ body: PROJECT })),
    )
    await flushPromises()

    expect(wrapper.get(`a[href="/projects/${PROJECT_ID}/import"]`).text()).toBe(
      messages.overview.importAction,
    )
  })

  it('shows a load error and retries when the project fails to load', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(
        signedInRoutes({
          body: { error: { code: 'resource_not_found', message: 'Gone.' } },
          init: { status: 404 },
        }),
      ),
    )
    await flushPromises()

    expect(wrapper.get('main').text()).toContain(messages.overview.loadError)
  })

  it('redirects a signed-out visitor to the login page', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': {
          body: {
            error: { code: 'authentication_required', message: 'Authentication is required.' },
          },
          init: { status: 401 },
        },
      }),
    )

    // /login is lazy; its first import in this test file's process needs more than one
    // macrotask tick to resolve. See tests/helpers/wait.ts.
    await waitFor(() => {
      expect(wrapper.get('main h1').text()).toBe(catalogues[locale].login.title)
    })
  })
})
