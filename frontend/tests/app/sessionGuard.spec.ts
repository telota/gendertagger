import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, type Router } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient, type ApiClient } from '@/api'
import { createAppRouter } from '@/app/router'
import {
  privateRetryScope,
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
  const instance = createAppRouter(createMemoryHistory())
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
        retryScope: privateRetryScope,
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
      if (!changesBefore401) {
        await waitFor(() => expect(useSessionRecovery().isOpen.value).toBe(true))
        session.user = recovered
        useSessionRecovery().resolve()
      }

      const result = await pending

      expect(attempts).toHaveLength(replays ? 2 : 1)
      expect(result.response.status).toBe(replays ? 201 : 401)
      expect(session.user?.id).toBe(recovered.id)
      expect(activeRouter.currentRoute.value.path).toBe('/')
      expect(privateRetryScope(request('/api/v1/annotations'))).toBe(
        `${recovered.id}:${session.principalRevision}`,
      )
      expect(
        privateRetryScope(
          new Request('https://example.test/api/v1/me/password', { method: 'POST' }),
        ),
      ).toBe(`${recovered.id}:${session.principalRevision}`)
    },
  )
})

describe('private request retry ownership', () => {
  it.each([
    '/api/v1/branding',
    '/api/v1/public/classify',
    '/api/v1/public/methods',
    '/api/v1/public/classification-jobs/20000000-0000-0000-0000-000000000001',
  ])('keeps the public request %s outside private account ownership', (path) => {
    expect(privateRetryScope(request(path))).toBeNull()
  })

  const operations = [
    {
      name: 'private export read',
      replays: true,
      dispatch: (client: ApiClient) =>
        client.GET('/api/v1/exports/{export_execution_id}', {
          params: { path: { export_execution_id: '20000000-0000-0000-0000-000000000001' } },
        }),
    },
    {
      name: 'run creation command',
      replays: true,
      dispatch: (client: ApiClient) =>
        client.POST('/api/v1/runs', {
          body: {
            dataset_snapshot_id: '20000000-0000-0000-0000-000000000001',
            config: { methods: [{ name: 'gender_guesser', enabled: true, config: {} }] },
          },
        }),
    },
    {
      name: 'non-replaying private preference read',
      replays: false,
      dispatch: (client: ApiClient) => client.GET('/api/v1/me/preferences'),
    },
  ]
  const recoveries = [
    { name: 'same-account recovery', principals: [USER], before401: false, sameOwner: true },
    { name: 'account replacement', principals: [OTHER_USER], before401: false, sameOwner: false },
    {
      name: 'A to B to A replacement',
      principals: [OTHER_USER, USER],
      before401: false,
      sameOwner: false,
    },
    {
      name: 'logout then same-account sign-in',
      principals: [null, USER],
      before401: false,
      sameOwner: false,
    },
    {
      name: 'late 401 after account replacement',
      principals: [OTHER_USER],
      before401: true,
      sameOwner: false,
    },
    {
      name: 'late 401 after A to B to A replacement',
      principals: [OTHER_USER, USER],
      before401: true,
      sameOwner: false,
    },
    {
      name: 'late 401 after logout then same-account sign-in',
      principals: [null, USER],
      before401: true,
      sameOwner: false,
    },
  ]

  describe.each(operations)('$name', ({ dispatch, replays }) => {
    it.each(recoveries)('handles $name without recovering an obsolete owner', async (recovery) => {
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
        retryScope: privateRetryScope,
        fetch: (request) => {
          attempts.push(request)
          return attempts.length === 1
            ? firstResponse
            : Promise.resolve(
                new Response('{}', { headers: { 'content-type': 'application/json' } }),
              )
        },
      })
      const pending = dispatch(client)
      await waitFor(() => expect(attempts).toHaveLength(1))
      function replacePrincipal(): void {
        for (const principal of recovery.principals) session.user = principal
      }
      if (recovery.before401) replacePrincipal()
      finishFirst(
        new Response(
          JSON.stringify({
            error: { code: 'authentication_required', message: 'Session expired.' },
          }),
          { status: 401, headers: { 'content-type': 'application/json' } },
        ),
      )
      if (!recovery.before401) {
        await waitFor(() => expect(useSessionRecovery().isOpen.value).toBe(true))
        replacePrincipal()
        useSessionRecovery().resolve()
      }

      const result = await pending
      const shouldReplay = replays && recovery.sameOwner
      expect(attempts).toHaveLength(shouldReplay ? 2 : 1)
      expect(result.response.status).toBe(shouldReplay ? 200 : 401)
      expect(useSessionRecovery().isOpen.value).toBe(false)
      expect(session.user?.id).toBe(recovery.principals.at(-1)?.id)
      expect(activeRouter.currentRoute.value.path).toBe('/')
      if (shouldReplay) {
        expect(attempts[1]?.url).toBe(attempts[0]?.url)
        expect(attempts[1]?.method).toBe(attempts[0]?.method)
        if (attempts[0]?.method === 'POST') {
          expect(await attempts[1]!.clone().json()).toEqual(await attempts[0].clone().json())
        }
      }
    })
  })

  it.each([
    { name: 'another account', principals: [OTHER_USER] },
    { name: 'A to B to A replacement', principals: [OTHER_USER, USER] },
  ])('keeps $name when an obsolete recovery prompt is declined', async ({ principals }) => {
    const session = mountSession(
      apiClientWithRoutes({
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
      }),
    )
    await session.initialize()
    const activeRouter = await router()
    await activeRouter.push('/change-password')
    const pending = createUnauthorizedHandler(activeRouter)(request('/api/v1/exports/old-export'))
    expect(useSessionRecovery().isOpen.value).toBe(true)
    for (const principal of principals) session.user = principal

    useSessionRecovery().reject(new Error('declined obsolete recovery'))

    await expect(pending).rejects.toThrow('declined obsolete recovery')
    expect(session.user?.id).toBe(principals.at(-1)?.id)
    expect(session.isSignedIn).toBe(true)
    expect(activeRouter.currentRoute.value.path).toBe('/change-password')
  })
})
