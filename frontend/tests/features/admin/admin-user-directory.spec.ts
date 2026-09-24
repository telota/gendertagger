import { flushPromises } from '@vue/test-utils'
import { getActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import { useSessionStore } from '@/stores/session'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../../helpers/api'
import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const
const ADMIN_A = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Admin A',
  roles: ['admin'],
}
const ADMIN_B = {
  id: 'a0000000-0000-0000-0000-000000000002',
  display_name: 'Admin B',
  roles: ['admin'],
}
const OPERATOR = {
  id: 'a0000000-0000-0000-0000-000000000003',
  display_name: 'Operator',
  roles: ['operator'],
}
const ACCOUNT_A = {
  id: 'b0000000-0000-0000-0000-000000000001',
  username: 'alpha',
  display_name: 'Alpha Account',
  roles: ['admin'],
  is_active: true,
  must_change_password: false,
  created_at: '2026-09-24T00:00:00Z',
}
const ACCOUNT_B = {
  id: 'b0000000-0000-0000-0000-000000000002',
  username: 'bravo',
  display_name: 'Bravo Account',
  roles: ['operator'],
  is_active: false,
  must_change_password: true,
  created_at: '2026-09-24T00:00:00Z',
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function signedInRoutes(
  user: { id: string; display_name: string; roles: string[] },
  directory: RouteResponse = { body: { items: [], has_more: false, next_cursor: null } },
  mustChangePassword = false,
): Record<string, RouteResponse> {
  return {
    '/api/v1/branding': { body: {} },
    '/api/v1/me': { body: user },
    '/api/v1/auth/session': {
      body: { must_change_password: mustChangePassword, keep_signed_in: false },
    },
    '/api/v1/admin/users': directory,
  }
}

function currentSession() {
  const pinia = getActivePinia()
  if (!pinia) throw new Error('The mounted application must install Pinia.')
  return useSessionStore(pinia)
}

function buttonWithText(
  wrapper: {
    findAll: (
      selector: string,
    ) => { text: () => string; trigger: (event: string) => Promise<void> }[]
  },
  text: string,
) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text() === text)
  if (!button) throw new Error(`Button ${text} was not rendered.`)
  return button
}

afterEach(() => {
  vi.useRealTimers()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('AdminUserDirectoryView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].admin

  it('shows the administrative navigation only to a password-current global administrator', async () => {
    const administrator = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes(signedInRoutes(ADMIN_A)),
    )
    await waitFor(() => {
      expect(administrator.get('aside a[href="/admin/users"]').text()).toBe(
        catalogues[locale].nav.administration,
      )
    })
    administrator.unmount()

    const operator = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes(signedInRoutes(OPERATOR)),
    )
    expect(operator.find('aside a[href="/admin/users"]').exists()).toBe(false)
  })

  it('keeps the navigation hidden while a password change is required', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes(signedInRoutes(ADMIN_A, undefined, true)),
    )

    await flushPromises()
    expect(wrapper.find('aside a[href="/admin/users"]').exists()).toBe(false)
  })

  it('redirects a signed-out direct visit to login and preserves its destination', async () => {
    const wrapper = await mountApplicationAt(
      '/admin/users',
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

    await waitFor(() => {
      expect(wrapper.get('main h1').text()).toBe(catalogues[locale].login.title)
    })
  })

  it('routes a password-change-required administrator through the existing change-password view', async () => {
    const wrapper = await mountApplicationAt(
      '/admin/users',
      locale,
      apiClientWithRoutes(signedInRoutes(ADMIN_A, undefined, true)),
    )

    await waitFor(() => {
      expect(wrapper.get('main h1').text()).toBe(catalogues[locale].changePassword.title)
    })
  })

  it('renders a clear permission state for a signed-in non-administrator', async () => {
    const wrapper = await mountApplicationAt(
      '/admin/users',
      locale,
      apiClientWithRoutes(signedInRoutes(OPERATOR)),
    )

    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe(messages.forbidden)
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('keeps a failed session check distinct from a signed-out visit', async () => {
    const wrapper = await mountApplicationAt(
      '/admin/users',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': {
          body: { error: { code: 'internal_error', message: 'The server failed.' } },
          init: { status: 500 },
        },
      }),
    )

    await flushPromises()
    expect(wrapper.get('main [role="alert"]').text()).toBe(messages.sessionLoadError)
  })

  it('renders the server order, account states, and current account marker', async () => {
    const wrapper = await mountApplicationAt(
      '/admin/users',
      locale,
      apiClientWithRoutes(
        signedInRoutes(ADMIN_A, {
          body: {
            items: [ACCOUNT_B, { ...ACCOUNT_A, id: ADMIN_A.id }],
            has_more: false,
            next_cursor: null,
          },
        }),
      ),
    )

    await waitFor(() => {
      expect(wrapper.findAll('tbody tr').map((row) => row.text())).toEqual([
        expect.stringContaining(ACCOUNT_B.username),
        expect.stringContaining(ACCOUNT_A.username),
      ])
    })
    expect(wrapper.text()).toContain(messages.currentAccount)
    expect(wrapper.text()).toContain(messages.states.inactive)
    expect(wrapper.text()).toContain(messages.states.passwordChangeRequired)
    await expectNoAxeViolations(wrapper.element)
  })

  it('debounces the server-side search and starts a new cursor sequence', async () => {
    vi.useFakeTimers()
    const requests: URL[] = []
    const client = createApiClient({
      fetch: (request: Request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (url.pathname === '/api/v1/me') return Promise.resolve(jsonResponse(ADMIN_A))
        if (url.pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (url.pathname === '/api/v1/admin/users') {
          requests.push(url)
          return Promise.resolve(jsonResponse({ items: [], has_more: false, next_cursor: null }))
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/admin/users', locale, client)
    await vi.advanceTimersByTimeAsync(0)
    await flushPromises()
    expect(requests).toHaveLength(1)

    await wrapper.get('#admin-user-search').setValue('Ada')
    await vi.advanceTimersByTimeAsync(299)
    await flushPromises()
    expect(requests).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(1)
    await flushPromises()
    expect(requests).toHaveLength(2)
    expect(requests[1]?.searchParams.get('query')).toBe('Ada')
    expect(requests[1]?.searchParams.get('cursor')).toBeNull()
  })

  it('offers retry after an initial directory error', async () => {
    let directoryRequests = 0
    const client = createApiClient({
      fetch: (request: Request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(ADMIN_A))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === '/api/v1/admin/users') {
          directoryRequests += 1
          return Promise.resolve(
            directoryRequests === 1
              ? jsonResponse({ error: { code: 'internal_error', message: 'No.' } }, { status: 500 })
              : jsonResponse({ items: [ACCOUNT_A], has_more: false, next_cursor: null }),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/admin/users', locale, client)
    await waitFor(() => {
      expect(wrapper.get('[role="alert"]').text()).toBe(messages.loadError)
    })

    await buttonWithText(wrapper, messages.retry).trigger('click')
    await waitFor(() => {
      expect(wrapper.text()).toContain(ACCOUNT_A.username)
    })
  })

  it('keeps loaded rows when cursor pagination fails and offers a targeted retry', async () => {
    let directoryRequests = 0
    const cursors: (string | null)[] = []
    const client = createApiClient({
      fetch: (request: Request) => {
        const url = new URL(request.url)
        const { pathname } = url
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(ADMIN_A))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === '/api/v1/admin/users') {
          cursors.push(url.searchParams.get('cursor'))
          directoryRequests += 1
          return Promise.resolve(
            directoryRequests === 1
              ? jsonResponse({ items: [ACCOUNT_A], has_more: true, next_cursor: 'opaque-cursor' })
              : jsonResponse(
                  { error: { code: 'internal_error', message: 'No.' } },
                  { status: 500 },
                ),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/admin/users', locale, client)
    await waitFor(() => {
      expect(wrapper.text()).toContain(ACCOUNT_A.username)
    })

    await buttonWithText(wrapper, messages.loadMore).trigger('click')
    await waitFor(() => {
      expect(wrapper.text()).toContain(messages.paginationError)
    })
    expect(wrapper.text()).toContain(ACCOUNT_A.username)
    expect(cursors).toEqual([null, 'opaque-cursor'])
  })

  it('removes late responses from a former administrator identity', async () => {
    let currentUser = ADMIN_A
    let resolveFormerDirectory: ((response: Response) => void) | undefined
    const client = createApiClient({
      fetch: (request: Request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(currentUser))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === '/api/v1/admin/users' && currentUser.id === ADMIN_A.id) {
          return new Promise<Response>((resolve) => {
            resolveFormerDirectory = resolve
          })
        }
        if (pathname === '/api/v1/admin/users') {
          return Promise.resolve(
            jsonResponse({ items: [ACCOUNT_B], has_more: false, next_cursor: null }),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/admin/users', locale, client)
    await flushPromises()

    currentUser = ADMIN_B
    await currentSession().initialize()
    await waitFor(() => {
      expect(wrapper.text()).toContain(ACCOUNT_B.username)
    })

    resolveFormerDirectory?.(
      jsonResponse({ items: [ACCOUNT_A], has_more: false, next_cursor: null }),
    )
    await flushPromises()
    expect(wrapper.text()).not.toContain(ACCOUNT_A.username)
    expect(wrapper.text()).toContain(ACCOUNT_B.username)
  })
})
