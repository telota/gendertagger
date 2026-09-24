import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../../helpers/api'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

const catalogues = { de, en } as const

const VIEWER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Viewer One', roles: [] }
const OPERATOR = {
  id: 'a0000000-0000-0000-0000-000000000002',
  display_name: 'Operator One',
  roles: ['operator'],
}

const PROJECT_A = {
  id: 'b0000000-0000-0000-0000-000000000001',
  slug: 'project-a',
  display_name: 'Project A',
  description: 'The first project.',
  team: {
    id: 'c0000000-0000-0000-0000-000000000001',
    slug: 'editorial-team',
    display_name: 'Editorial team',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  manager_user_id: OPERATOR.id,
  created_by_user_id: OPERATOR.id,
  current_user_role: 'viewer',
  current_user_can_manage_members: false,
  created_at: '2026-01-01T00:00:00Z',
}

function signedInRoutes(
  user: { id: string; display_name: string; roles: string[] },
  projectsBody: RouteResponse,
): Record<string, RouteResponse> {
  return {
    '/api/v1/branding': { body: {} },
    '/api/v1/me': { body: user },
    '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    '/api/v1/projects': projectsBody,
  }
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('ProjectListView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projects

  it('redirects a signed-out visitor to the login page', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
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

  it('shows a load error and a retry when the session itself cannot be checked', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': {
          body: { error: { code: 'internal_error', message: 'Something went wrong.' } },
          init: { status: 500 },
        },
      }),
    )
    await flushPromises()

    expect(wrapper.get('main').text()).toContain(messages.sessionLoadError)
  })

  it('shows the empty state when there are no projects', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
      locale,
      apiClientWithRoutes(
        signedInRoutes(VIEWER, { body: { items: [], has_more: false, next_cursor: null } }),
      ),
    )
    await flushPromises()

    expect(wrapper.get('main').text()).toContain(messages.empty)
  })

  it('lists a project with its role, and offers no creation action to a viewer', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
      locale,
      apiClientWithRoutes(
        signedInRoutes(VIEWER, {
          body: { items: [PROJECT_A], has_more: false, next_cursor: null },
        }),
      ),
    )
    await flushPromises()

    expect(wrapper.text()).toContain('Project A')
    expect(wrapper.text()).toContain('The first project.')
    expect(wrapper.text()).toContain(messages.role.viewer)
    expect(wrapper.find('.project-list-new-project').exists()).toBe(false)
  })

  it('does not expose project creation until the team-selection UI is available', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
      locale,
      apiClientWithRoutes(
        signedInRoutes(OPERATOR, { body: { items: [], has_more: false, next_cursor: null } }),
      ),
    )
    await flushPromises()

    expect(wrapper.find('.project-list-new-project').exists()).toBe(false)
  })

  it('shows a load error and retries when asked to', async () => {
    let calls = 0
    const client = createApiClient({
      fetch: (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(VIEWER))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === '/api/v1/projects') {
          calls += 1
          if (calls === 1) {
            return Promise.resolve(
              jsonResponse(
                { error: { code: 'internal_error', message: 'Something went wrong.' } },
                { status: 500 },
              ),
            )
          }
          return Promise.resolve(
            jsonResponse({ items: [PROJECT_A], has_more: false, next_cursor: null }),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    await flushPromises()
    expect(wrapper.get('main').text()).toContain(messages.loadError)

    await wrapper.get('.project-list-retry').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Project A')
  })

  it('loads the next page on request', async () => {
    let calls = 0
    const client = createApiClient({
      fetch: (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(VIEWER))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === '/api/v1/projects') {
          calls += 1
          return Promise.resolve(
            jsonResponse(
              calls === 1
                ? { items: [PROJECT_A], has_more: true, next_cursor: 'cursor-1' }
                : {
                    items: [
                      {
                        ...PROJECT_A,
                        id: 'b0000000-0000-0000-0000-000000000002',
                        slug: 'project-b',
                        display_name: 'Project B',
                      },
                    ],
                    has_more: false,
                    next_cursor: null,
                  },
            ),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    await flushPromises()
    expect(wrapper.text()).toContain('Project A')
    expect(wrapper.text()).not.toContain('Project B')

    await wrapper.get('.project-list-load-more').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Project A')
    expect(wrapper.text()).toContain('Project B')
    expect(calls).toBe(2)
  })

})
