import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient, type ApiClient } from '@/api'
import { routes } from '@/app/router'
import {
  annotationRetryScope,
  createUnauthorizedHandler,
  shouldRetryAfterUnauthorized,
} from '@/app/sessionGuard'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { useSessionRecovery } from '@/composables/useSessionRecovery'
import { useSessionStore } from '@/stores/session'

import { apiClientWithRoutes } from '../helpers/api'
import { waitFor } from '../helpers/wait'

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const OTHER_USER = {
  ...USER,
  id: 'a0000000-0000-0000-0000-000000000002',
  display_name: 'Reviewer Two',
}

function request(path: string): Request {
  return new Request(`https://example.test${path}`)
}

/** Pinia's inject()-in-setup-stores support needs a real mounted component and an installed app. */
function mountSession(client: ApiClient) {
  let store!: ReturnType<typeof useSessionStore>
  mount(
    defineComponent({
      setup() {
        store = useSessionStore()
        return () => null
      },
    }),
    { global: { plugins: [createPinia()], provide: { [API_CLIENT_KEY as symbol]: client } } },
  )
  return store
}

async function router(): Promise<Router> {
  const instance = createRouter({ history: createMemoryHistory(), routes: [...routes] })
  await instance.push('/')
  await instance.isReady()
  return instance
}

afterEach(() => {
  // Settle any prompt a test left open so it cannot leak into the next test.
  useSessionRecovery().reject(new Error('test cleanup'))
})

describe('shouldRetryAfterUnauthorized', () => {
  it('excludes administrative account, team, and settings writes from automatic replay', () => {
    expect(
      shouldRetryAfterUnauthorized(
        new Request('https://example.test/api/v1/admin/users', { method: 'POST' }),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request(
          'https://example.test/api/v1/admin/users/6f9619ff-8b86-4011-b42d-00c04fc964ff',
          { method: 'PATCH' },
        ),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request(
          'https://example.test/api/v1/admin/users/6f9619ff-8b86-4011-b42d-00c04fc964ff/reset-password',
          { method: 'POST' },
        ),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request(
          'https://example.test/api/v1/admin/users/6f9619ff-8b86-4011-b42d-00c04fc964ff/revoke-sessions',
          { method: 'POST' },
        ),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request('https://example.test/api/v1/admin/settings', { method: 'PATCH' }),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request('https://example.test/api/v1/admin/settings/reset', { method: 'POST' }),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request('https://example.test/api/v1/admin/teams', { method: 'POST' }),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request(
          'https://example.test/api/v1/admin/teams/6f9619ff-8b86-4011-b42d-00c04fc964ff',
          { method: 'PATCH' },
        ),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request(
          'https://example.test/api/v1/admin/teams/6f9619ff-8b86-4011-b42d-00c04fc964ff',
          { method: 'DELETE' },
        ),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request(
          'https://example.test/api/v1/admin/teams/6f9619ff-8b86-4011-b42d-00c04fc964ff/members',
          { method: 'POST' },
        ),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request(
          'https://example.test/api/v1/admin/teams/6f9619ff-8b86-4011-b42d-00c04fc964ff/members/7f9619ff-8b86-4011-b42d-00c04fc964ff',
          { method: 'DELETE' },
        ),
      ),
    ).toBe(false)
    expect(
      shouldRetryAfterUnauthorized(
        new Request('https://example.test/api/v1/me/password', { method: 'POST' }),
      ),
    ).toBe(true)
  })
})
describe('createUnauthorizedHandler', () => {
  it('never opens a prompt for the login endpoint', async () => {
    const handler = createUnauthorizedHandler(await router())

    await expect(handler(request('/api/v1/auth/login'))).rejects.toThrow()
    expect(useSessionRecovery().isOpen.value).toBe(false)
  })

  it('never opens a prompt for the logout endpoint', async () => {
    const handler = createUnauthorizedHandler(await router())

    await expect(handler(request('/api/v1/auth/logout'))).rejects.toThrow()
    expect(useSessionRecovery().isOpen.value).toBe(false)
  })

  it('never opens a prompt when there is no signed-in session to recover', async () => {
    mountSession(apiClientWithRoutes({}))
    const handler = createUnauthorizedHandler(await router())

    await expect(handler(request('/api/v1/projects'))).rejects.toThrow()
    expect(useSessionRecovery().isOpen.value).toBe(false)
  })

  it('opens a prompt and resolves once the user signs in again, without navigating away', async () => {
    const session = mountSession(
      apiClientWithRoutes({
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
      }),
    )
    await session.initialize()
    const activeRouter = await router()
    const handler = createUnauthorizedHandler(activeRouter)

    const pending = handler(request('/api/v1/projects'))
    expect(useSessionRecovery().isOpen.value).toBe(true)

    useSessionRecovery().resolve()
    await pending

    expect(session.isSignedIn).toBe(true)
    expect(activeRouter.currentRoute.value.path).toBe('/')
  })

  it('forgets the session and routes to login, preserving the page, when the user declines', async () => {
    const session = mountSession(
      apiClientWithRoutes({
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
      }),
    )
    await session.initialize()
    const activeRouter = await router()
    await activeRouter.push('/change-password')
    const handler = createUnauthorizedHandler(activeRouter)

    const pending = handler(request('/api/v1/projects'))
    useSessionRecovery().reject(new Error('declined'))

    await expect(pending).rejects.toThrow('declined')
    expect(session.isSignedIn).toBe(false)
    expect(activeRouter.currentRoute.value.name).toBe('login')
    expect(activeRouter.currentRoute.value.query.redirect).toBe('/change-password')
  })

  it('does not navigate again when the user was already on the login page', async () => {
    const session = mountSession(
      apiClientWithRoutes({
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
      }),
    )
    await session.initialize()
    const activeRouter = await router()
    await activeRouter.push('/login')
    const handler = createUnauthorizedHandler(activeRouter)

    const pending = handler(request('/api/v1/projects'))
    useSessionRecovery().reject(new Error('declined'))

    await expect(pending).rejects.toThrow('declined')
    expect(activeRouter.currentRoute.value.name).toBe('login')
    expect(activeRouter.currentRoute.value.query.redirect).toBeUndefined()
  })
})

describe('annotation retry ownership', () => {
  it.each([
    { name: 'same-account recovery', recovered: USER, changesBefore401: false, replays: true },
    {
      name: 'different-account recovery',
      recovered: OTHER_USER,
      changesBefore401: false,
      replays: false,
    },
    {
      name: 'an account change before the 401 arrives',
      recovered: OTHER_USER,
      changesBefore401: true,
      replays: false,
    },
  ])(
    'handles $name without changing an annotation author',
    async ({ recovered, changesBefore401, replays }) => {
      const session = mountSession(
        apiClientWithRoutes({
          '/api/v1/me': { body: USER },
          '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
        }),
      )
      await session.initialize()
      const activeRouter = await router()
      let finishFirst!: (response: Response) => void
      const firstResponse = new Promise<Response>((resolve) => {
        finishFirst = resolve
      })
      const attempts: Request[] = []
      const client = createApiClient({
        csrfToken: () => 'csrf',
        onUnauthorized: createUnauthorizedHandler(activeRouter),
        shouldRetryAfterUnauthorized,
        retryScope: annotationRetryScope,
        fetch: (request) => {
          attempts.push(request)
          return attempts.length === 1
            ? firstResponse
            : Promise.resolve(
                new Response('{}', {
                  status: 201,
                  headers: { 'content-type': 'application/json' },
                }),
              )
        },
      })
      const pending = client.POST('/api/v1/annotations', {
        body: {
          snapshot_id: '20000000-0000-0000-0000-000000000001',
          tei_id: 'p1',
          action: 'correct',
          label: 'unknown',
          expected_revision: 0,
        },
      })
      await waitFor(() => expect(attempts).toHaveLength(1))
      if (changesBefore401) session.user = recovered
      finishFirst(
        new Response(
          JSON.stringify({
            error: { code: 'authentication_required', message: 'Session expired.' },
          }),
          { status: 401, headers: { 'content-type': 'application/json' } },
        ),
      )
      await waitFor(() => expect(useSessionRecovery().isOpen.value).toBe(true))
      if (!changesBefore401) session.user = recovered
      useSessionRecovery().resolve()

      const result = await pending

      expect(attempts).toHaveLength(replays ? 2 : 1)
      expect(result.response.status).toBe(replays ? 201 : 401)
      expect(session.user?.id).toBe(recovered.id)
      expect(activeRouter.currentRoute.value.path).toBe('/')
      expect(annotationRetryScope(request('/api/v1/annotations'))).toBeNull()
      expect(
        annotationRetryScope(
          new Request('https://example.test/api/v1/me/password', { method: 'POST' }),
        ),
      ).toBeNull()
    },
  )
})
