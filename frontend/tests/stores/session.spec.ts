import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { createApiClient, type ApiClient } from '@/api'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { useSessionStore } from '@/stores/session'

import { apiClientWithNetworkError, apiClientWithRoutes } from '../helpers/api'
import { waitFor } from '../helpers/wait'

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const REPLACEMENT_USER = { ...USER, id: 'a0000000-0000-0000-0000-000000000002' }

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

function sessionFlags(mustChangePassword: boolean): Response {
  return Response.json({ must_change_password: mustChangePassword, keep_signed_in: false })
}

function lateResponse(status: number, successfulBody: unknown): Response {
  return Response.json(
    status === 200
      ? successfulBody
      : { error: { code: 'obsolete_session', message: 'The old request failed.' } },
    { status },
  )
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
    {
      global: {
        plugins: [createPinia()],
        provide: { [API_CLIENT_KEY as symbol]: client },
      },
    },
  )
  return store
}

describe('useSessionStore.initialize', () => {
  it('resolves a signed-in user and its session flags', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: true, keep_signed_in: false } },
      }),
    )

    await store.initialize()

    expect(store.status).toBe('ready')
    expect(store.isSignedIn).toBe(true)
    expect(store.user).toEqual(USER)
    expect(store.mustChangePassword).toBe(true)
  })

  it('treats a missing session as ordinary signed-out state, not an error', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/me': {
          body: {
            error: { code: 'authentication_required', message: 'Authentication is required.' },
          },
          init: { status: 401 },
        },
      }),
    )

    await store.initialize()

    expect(store.status).toBe('ready')
    expect(store.isSignedIn).toBe(false)
    expect(store.user).toBeNull()
  })

  it('reports a server error as a distinct status, not the ordinary signed-out state', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/me': {
          body: { error: { code: 'internal_error', message: 'Something went wrong.' } },
          init: { status: 500 },
        },
      }),
    )

    await store.initialize()

    expect(store.status).toBe('error')
    expect(store.user).toBeNull()
  })

  it('reports a network failure as the same distinct error status', async () => {
    const store = mountSession(apiClientWithNetworkError())

    await store.initialize()

    expect(store.status).toBe('error')
  })

  it('reports an error, without discarding the user, if the session flags fail to load', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': {
          body: { error: { code: 'internal_error', message: 'Something went wrong.' } },
          init: { status: 500 },
        },
      }),
    )

    await store.initialize()

    expect(store.status).toBe('error')
    expect(store.user).toEqual(USER)
  })

  it.each([200, 401, 500])(
    'ignores a late HTTP %s principal read after another account signs in',
    async (status) => {
      const pendingUser = deferredResponse()
      let flagReads = 0
      const store = mountSession(
        createApiClient({
          fetch: async (request) => {
            const path = new URL(request.url).pathname
            if (path === '/api/v1/me') return pendingUser.promise
            if (path === '/api/v1/auth/login') return Response.json(REPLACEMENT_USER)
            flagReads += 1
            return sessionFlags(true)
          },
        }),
      )
      store.user = USER
      store.status = 'ready'
      const initializing = store.initialize()
      await store.login({ username: 'replacement', password: 'correct', keepSignedIn: false })
      const revision = store.principalRevision

      pendingUser.resolve(lateResponse(status, USER))
      await initializing

      expect(store.user).toEqual(REPLACEMENT_USER)
      expect(store.mustChangePassword).toBe(true)
      expect(store.status).toBe('ready')
      expect(store.isAuthenticating).toBe(false)
      expect(store.principalRevision).toBe(revision)
      expect(flagReads).toBe(1)
    },
  )

  it.each([200, 401, 500])(
    'ignores late HTTP %s initialization flags after another account signs in',
    async (status) => {
      const pendingFlags = deferredResponse()
      let flagReads = 0
      const store = mountSession(
        createApiClient({
          fetch: async (request) => {
            const path = new URL(request.url).pathname
            if (path === '/api/v1/me') return Response.json(USER)
            if (path === '/api/v1/auth/login') return Response.json(REPLACEMENT_USER)
            flagReads += 1
            return flagReads === 1 ? pendingFlags.promise : sessionFlags(true)
          },
        }),
      )
      store.user = USER
      store.status = 'ready'
      const initializing = store.initialize()
      await waitFor(() => expect(flagReads).toBe(1))
      await store.login({ username: 'replacement', password: 'correct', keepSignedIn: false })

      pendingFlags.resolve(
        lateResponse(status, { must_change_password: false, keep_signed_in: false }),
      )
      await initializing

      expect(store.user).toEqual(REPLACEMENT_USER)
      expect(store.mustChangePassword).toBe(true)
      expect(store.status).toBe('ready')
      expect(store.canUsePrivateNavigation).toBe(false)
    },
  )

  it.each(['forget', 'logout'] as const)(
    'does not restore a forgotten principal when initialization settles after %s',
    async (action) => {
      const pendingUser = deferredResponse()
      let flagReads = 0
      const store = mountSession(
        createApiClient({
          fetch: async (request) => {
            const path = new URL(request.url).pathname
            if (path === '/api/v1/me') return pendingUser.promise
            if (path === '/api/v1/auth/logout') return new Response(null, { status: 204 })
            flagReads += 1
            return sessionFlags(true)
          },
        }),
      )
      store.user = USER
      store.status = 'ready'
      const initializing = store.initialize()
      if (action === 'forget') store.forgetSession()
      else await store.logout()
      expect(store.status).toBe('ready')
      const revision = store.principalRevision

      pendingUser.resolve(Response.json(USER))
      await initializing

      expect(store.user).toBeNull()
      expect(store.mustChangePassword).toBe(false)
      expect(store.status).toBe('ready')
      expect(store.canUsePrivateNavigation).toBe(false)
      expect(store.principalRevision).toBe(revision)
      expect(flagReads).toBe(0)
    },
  )

  it('does not initialize over an active login', async () => {
    const pendingFlags = deferredResponse()
    let principalReads = 0
    let flagReads = 0
    const store = mountSession(
      createApiClient({
        fetch: async (request) => {
          const path = new URL(request.url).pathname
          if (path === '/api/v1/auth/login') return Response.json(REPLACEMENT_USER)
          if (path === '/api/v1/me') {
            principalReads += 1
            return Response.json(USER)
          }
          flagReads += 1
          return pendingFlags.promise
        },
      }),
    )
    const signingIn = store.login({
      username: 'replacement',
      password: 'correct',
      keepSignedIn: false,
    })
    await waitFor(() => expect(flagReads).toBe(1))

    await store.initialize()
    expect(principalReads).toBe(0)
    expect(store.isAuthenticating).toBe(true)
    expect(store.user).toEqual(REPLACEMENT_USER)
    pendingFlags.resolve(sessionFlags(true))
    await signingIn
    expect(store.mustChangePassword).toBe(true)
  })

  it('does not restore an earlier principal read over same-account reauthentication', async () => {
    const pendingUser = deferredResponse()
    const renewedUser = { ...USER, display_name: 'Renewed reviewer' }
    let flagReads = 0
    const store = mountSession(
      createApiClient({
        fetch: async (request) => {
          const path = new URL(request.url).pathname
          if (path === '/api/v1/me') return pendingUser.promise
          if (path === '/api/v1/auth/login') return Response.json(renewedUser)
          flagReads += 1
          return sessionFlags(true)
        },
      }),
    )
    store.user = USER
    store.status = 'ready'
    const revision = store.principalRevision
    const initializing = store.initialize()
    await store.login({ username: 'reviewer', password: 'correct', keepSignedIn: false })
    pendingUser.resolve(Response.json(USER))
    await initializing

    expect(store.user).toEqual(renewedUser)
    expect(store.principalRevision).toBe(revision)
    expect(store.mustChangePassword).toBe(true)
    expect(flagReads).toBe(1)
  })

  it('preserves same-account reauthentication when older initialization flags return 401', async () => {
    const pendingFlags = deferredResponse()
    let flagReads = 0
    const store = mountSession(
      createApiClient({
        fetch: async (request) => {
          const path = new URL(request.url).pathname
          if (path !== '/api/v1/auth/session') return Response.json(USER)
          flagReads += 1
          return flagReads === 1 ? pendingFlags.promise : sessionFlags(true)
        },
      }),
    )
    store.user = USER
    store.status = 'ready'
    const revision = store.principalRevision
    const initializing = store.initialize()
    await waitFor(() => expect(flagReads).toBe(1))
    await store.login({ username: 'reviewer', password: 'correct', keepSignedIn: false })
    pendingFlags.resolve(lateResponse(401, null))
    await initializing

    expect(store.user).toEqual(USER)
    expect(store.principalRevision).toBe(revision)
    expect(store.mustChangePassword).toBe(true)
    expect(store.status).toBe('ready')
  })
})

describe('useSessionStore.login', () => {
  it.each([false, true])(
    'waits for password-change flags before exposing navigation (required: %s)',
    async (mustChangePassword) => {
      let resolveFlags!: (response: Response) => void
      const flags = new Promise<Response>((resolve) => {
        resolveFlags = resolve
      })
      const store = mountSession(
        createApiClient({
          fetch: async (request) =>
            new URL(request.url).pathname === '/api/v1/auth/login' ? Response.json(USER) : flags,
        }),
      )
      store.status = 'ready'

      const signingIn = store.login({
        username: 'reviewer.one',
        password: 'correct',
        keepSignedIn: false,
      })
      await flushPromises()

      expect(store.isAuthenticating).toBe(true)
      expect(store.canUsePrivateNavigation).toBe(false)
      expect(store.user).toEqual(USER)
      // Recovery callers keep their form mounted while authentication resolves.
      expect(store.status).toBe('ready')

      resolveFlags(
        Response.json({ must_change_password: mustChangePassword, keep_signed_in: false }),
      )
      await signingIn

      expect(store.isAuthenticating).toBe(false)
      expect(store.user).toEqual(USER)
      expect(store.canUsePrivateNavigation).toBe(!mustChangePassword)
    },
  )

  it('keeps navigation hidden if credentials succeed but session flags fail', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/auth/login': { body: USER },
        '/api/v1/auth/session': {
          body: { error: { code: 'internal_error', message: 'Unavailable.' } },
          init: { status: 500 },
        },
      }),
    )
    store.status = 'ready'
    const previousUser = { ...USER, id: 'a0000000-0000-0000-0000-000000000002' }
    store.user = previousUser

    await expect(
      store.login({ username: 'reviewer.one', password: 'correct', keepSignedIn: false }),
    ).rejects.toMatchObject({ code: 'internal_error' })

    expect(store.status).toBe('error')
    expect(store.canUsePrivateNavigation).toBe(false)
    expect(store.isAuthenticating).toBe(false)
    expect(store.user).toEqual(USER)
  })

  it('sets the signed-in user and its session flags on success', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/auth/login': { body: USER, init: { status: 200 } },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: true } },
      }),
    )

    await store.login({
      username: 'reviewer.one',
      password: 'a-correct-passphrase',
      keepSignedIn: true,
    })

    expect(store.isSignedIn).toBe(true)
    expect(store.user).toEqual(USER)
    expect(store.mustChangePassword).toBe(false)
  })

  it('throws the classified ApiError and leaves the store signed out', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/auth/login': {
          body: { error: { code: 'invalid_credentials', message: 'Wrong.' } },
          init: { status: 401 },
        },
      }),
    )

    await expect(
      store.login({ username: 'reviewer.one', password: 'wrong', keepSignedIn: false }),
    ).rejects.toMatchObject({ code: 'invalid_credentials' })
    expect(store.isSignedIn).toBe(false)
  })

  it.each(['login', 'forget'] as const)(
    'rejects old login flags after a newer %s owns the session',
    async (action) => {
      const pendingFlags = deferredResponse()
      let loginCalls = 0
      let flagReads = 0
      const store = mountSession(
        createApiClient({
          fetch: async (request) => {
            if (new URL(request.url).pathname === '/api/v1/auth/login') {
              loginCalls += 1
              return Response.json(loginCalls === 1 ? USER : REPLACEMENT_USER)
            }
            flagReads += 1
            return flagReads === 1 ? pendingFlags.promise : sessionFlags(true)
          },
        }),
      )
      store.status = 'ready'
      const signingIn = store.login({ username: 'first', password: 'correct', keepSignedIn: false })
      const staleLogin = expect(signingIn).rejects.toMatchObject({ name: 'AbortError' })
      await waitFor(() => expect(flagReads).toBe(1))
      if (action === 'login')
        await store.login({ username: 'replacement', password: 'correct', keepSignedIn: false })
      else store.forgetSession()

      pendingFlags.resolve(sessionFlags(false))
      await staleLogin

      expect(store.user).toEqual(action === 'login' ? REPLACEMENT_USER : null)
      expect(store.mustChangePassword).toBe(action === 'login')
      expect(store.isAuthenticating).toBe(false)
      expect(store.status).toBe('ready')
    },
  )

  it('does not clear a newer login’s pending authentication when old flags arrive', async () => {
    const firstFlags = deferredResponse()
    const secondFlags = deferredResponse()
    let loginCalls = 0
    let flagReads = 0
    const store = mountSession(
      createApiClient({
        fetch: async (request) => {
          if (new URL(request.url).pathname === '/api/v1/auth/login') {
            loginCalls += 1
            return Response.json(loginCalls === 1 ? USER : REPLACEMENT_USER)
          }
          flagReads += 1
          return flagReads === 1 ? firstFlags.promise : secondFlags.promise
        },
      }),
    )
    const firstLogin = store.login({ username: 'first', password: 'correct', keepSignedIn: false })
    const staleLogin = expect(firstLogin).rejects.toMatchObject({ name: 'AbortError' })
    await waitFor(() => expect(flagReads).toBe(1))
    const secondLogin = store.login({
      username: 'replacement',
      password: 'correct',
      keepSignedIn: false,
    })
    await waitFor(() => expect(flagReads).toBe(2))

    firstFlags.resolve(sessionFlags(false))
    await staleLogin
    expect(store.user).toEqual(REPLACEMENT_USER)
    expect(store.isAuthenticating).toBe(true)
    expect(store.canUsePrivateNavigation).toBe(false)

    secondFlags.resolve(sessionFlags(true))
    await secondLogin
    expect(store.mustChangePassword).toBe(true)
    expect(store.isAuthenticating).toBe(false)
  })
})

describe('useSessionStore.logout', () => {
  it.each([204, 401, 500])(
    'ignores a late HTTP %s logout response after another account signs in',
    async (status) => {
      let resolveLogout!: (response: Response) => void
      const pendingLogout = new Promise<Response>((resolve) => {
        resolveLogout = resolve
      })
      const replacementUser = { ...USER, id: 'a0000000-0000-0000-0000-000000000002' }
      const store = mountSession(
        createApiClient({
          fetch: async (request) => {
            const { pathname } = new URL(request.url)
            if (pathname === '/api/v1/auth/logout') return pendingLogout
            if (pathname === '/api/v1/auth/login') return Response.json(replacementUser)
            return Response.json({ must_change_password: true, keep_signed_in: false })
          },
        }),
      )
      store.user = USER
      store.status = 'ready'
      const loggingOut = store.logout()
      await store.login({ username: 'replacement', password: 'correct', keepSignedIn: false })
      resolveLogout(
        status === 204
          ? new Response(null, { status })
          : Response.json({ error: { code: 'old_session', message: 'Old request.' } }, { status }),
      )

      await expect(loggingOut).resolves.toBe(false)
      expect(store.user).toEqual(replacementUser)
      expect(store.mustChangePassword).toBe(true)
      expect(store.status).toBe('ready')
    },
  )

  it('preserves a renewed session for the same account when an older logout resolves', async () => {
    let resolveLogout!: (response: Response) => void
    const pendingLogout = new Promise<Response>((resolve) => {
      resolveLogout = resolve
    })
    const store = mountSession(
      createApiClient({
        fetch: async (request) => {
          const { pathname } = new URL(request.url)
          if (pathname === '/api/v1/auth/logout') return pendingLogout
          if (pathname === '/api/v1/auth/login') return Response.json(USER)
          return Response.json({ must_change_password: false, keep_signed_in: false })
        },
      }),
    )
    store.user = USER
    store.status = 'ready'
    const loggingOut = store.logout()
    await store.login({ username: 'reviewer', password: 'correct', keepSignedIn: false })
    resolveLogout(new Response(null, { status: 204 }))

    await expect(loggingOut).resolves.toBe(false)
    expect(store.user).toEqual(USER)
    expect(store.isSignedIn).toBe(true)
  })

  it.each([204, 401, 500])(
    'ignores a late HTTP %s logout across A -> B -> A principal refreshes',
    async (status) => {
      const pendingLogout = deferredResponse()
      let authenticatedUser = USER
      const store = mountSession(
        createApiClient({
          fetch: async (request) => {
            const path = new URL(request.url).pathname
            if (path === '/api/v1/auth/logout') return pendingLogout.promise
            return path === '/api/v1/me' ? Response.json(authenticatedUser) : sessionFlags(false)
          },
        }),
      )
      store.user = USER
      store.status = 'ready'
      const loggingOut = store.logout()
      authenticatedUser = REPLACEMENT_USER
      await store.initialize()
      authenticatedUser = USER
      await store.initialize()

      pendingLogout.resolve(
        status === 204 ? new Response(null, { status }) : lateResponse(status, null),
      )
      await expect(loggingOut).resolves.toBe(false)

      expect(store.user).toEqual(USER)
      expect(store.isSignedIn).toBe(true)
      expect(store.status).toBe('ready')
    },
  )

  it('still applies logout after an ordinary refresh of the same account', async () => {
    let resolveLogout!: (response: Response) => void
    const pendingLogout = new Promise<Response>((resolve) => {
      resolveLogout = resolve
    })
    const store = mountSession(
      createApiClient({
        fetch: async (request) => {
          const { pathname } = new URL(request.url)
          if (pathname === '/api/v1/auth/logout') return pendingLogout
          if (pathname === '/api/v1/me') return Response.json(USER)
          return Response.json({ must_change_password: false, keep_signed_in: false })
        },
      }),
    )
    store.user = USER
    store.status = 'ready'
    const loggingOut = store.logout()
    await store.initialize()
    resolveLogout(new Response(null, { status: 204 }))

    await expect(loggingOut).resolves.toBe(true)
    expect(store.user).toBeNull()
    expect(store.status).toBe('ready')
  })

  it.each([403, 500])('retains the principal when logout fails with HTTP %s', async (status) => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/auth/logout': {
          body: { error: { code: 'logout_failed', message: 'Unavailable.' } },
          init: { status },
        },
      }),
    )
    store.user = USER
    store.mustChangePassword = true
    store.status = 'ready'

    await expect(store.logout()).rejects.toMatchObject({ status })

    expect(store.user).toEqual(USER)
    expect(store.mustChangePassword).toBe(true)
    expect(store.status).toBe('ready')
  })

  it('retains the principal when the logout response is lost', async () => {
    const store = mountSession(apiClientWithNetworkError())
    store.user = USER
    store.status = 'ready'

    await expect(store.logout()).rejects.toMatchObject({ code: 'network_error' })

    expect(store.user).toEqual(USER)
    expect(store.isSignedIn).toBe(true)
  })

  it('treats logout 401 as confirmation that the old session is gone', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/auth/logout': {
          body: { error: { code: 'authentication_required', message: 'Gone.' } },
          init: { status: 401 },
        },
      }),
    )
    store.user = USER
    store.mustChangePassword = true
    store.status = 'ready'

    await store.logout()

    expect(store.user).toBeNull()
    expect(store.mustChangePassword).toBe(false)
    expect(store.status).toBe('ready')
  })

  it('clears the session even though the store never verified it was signed in', async () => {
    const store = mountSession(
      apiClientWithRoutes({ '/api/v1/auth/logout': { body: null, init: { status: 204 } } }),
    )

    await store.logout()

    expect(store.isSignedIn).toBe(false)
    expect(store.mustChangePassword).toBe(false)
  })
})

describe('useSessionStore.forgetSession', () => {
  it('clears the local session state without any request', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: true, keep_signed_in: false } },
      }),
    )
    await store.initialize()
    expect(store.isSignedIn).toBe(true)

    store.forgetSession()

    expect(store.isSignedIn).toBe(false)
    expect(store.user).toBeNull()
    expect(store.mustChangePassword).toBe(false)
  })
})

describe('useSessionStore.principalRevision', () => {
  it('preserves same-account recovery ownership and advances across replacement and logout', async () => {
    let authenticatedUser = USER
    const store = mountSession(
      createApiClient({
        fetch: async (request) => {
          const path = new URL(request.url).pathname
          if (path === '/api/v1/auth/logout') return new Response(null, { status: 204 })
          return path === '/api/v1/auth/session'
            ? sessionFlags(false)
            : Response.json(authenticatedUser)
        },
      }),
    )
    store.user = USER
    store.status = 'ready'
    const revision = store.principalRevision
    const credentials = { username: 'reviewer', password: 'correct', keepSignedIn: false }

    await store.initialize()
    await store.login(credentials)
    expect(store.principalRevision).toBe(revision)

    await store.logout()
    expect(store.principalRevision).toBe(revision + 1)
    await store.login(credentials)
    expect(store.principalRevision).toBe(revision + 2)

    authenticatedUser = REPLACEMENT_USER
    await store.login(credentials)
    expect(store.principalRevision).toBe(revision + 3)
    authenticatedUser = USER
    await store.login(credentials)
    expect(store.principalRevision).toBe(revision + 4)
  })
})

describe('useSessionStore.changePassword', () => {
  it('clears the forced-change flag on success', async () => {
    const store = mountSession(
      apiClientWithRoutes({ '/api/v1/me/password': { body: null, init: { status: 204 } } }),
    )
    store.mustChangePassword = true

    await store.changePassword({
      currentPassword: 'old-passphrase-1',
      newPassword: 'new-passphrase-1',
    })

    expect(store.mustChangePassword).toBe(false)
  })

  it('throws the classified ApiError and keeps the forced-change flag', async () => {
    const store = mountSession(
      apiClientWithRoutes({
        '/api/v1/me/password': {
          body: { error: { code: 'invalid_current_password', message: 'Wrong.' } },
          init: { status: 400 },
        },
      }),
    )
    store.mustChangePassword = true

    await expect(
      store.changePassword({ currentPassword: 'wrong', newPassword: 'new-passphrase-1' }),
    ).rejects.toMatchObject({ code: 'invalid_current_password' })
    expect(store.mustChangePassword).toBe(true)
  })

  it.each([false, true])(
    'never clears a replacement session’s forced-change flag (return to A: %s)',
    async (returnToOriginal) => {
      const pendingPassword = deferredResponse()
      let authenticatedUser = REPLACEMENT_USER
      const store = mountSession(
        createApiClient({
          fetch: async (request) => {
            const path = new URL(request.url).pathname
            if (path === '/api/v1/me/password') return pendingPassword.promise
            return path === '/api/v1/auth/login'
              ? Response.json(authenticatedUser)
              : sessionFlags(true)
          },
        }),
      )
      store.user = USER
      store.mustChangePassword = true
      store.status = 'ready'
      const changing = store.changePassword({
        currentPassword: 'old-passphrase-1',
        newPassword: 'new-passphrase-1',
      })
      const staleChange = expect(changing).rejects.toMatchObject({ name: 'AbortError' })
      const credentials = { username: 'replacement', password: 'correct', keepSignedIn: false }
      await store.login(credentials)
      if (returnToOriginal) {
        authenticatedUser = USER
        await store.login(credentials)
      }

      pendingPassword.resolve(new Response(null, { status: 204 }))
      await staleChange

      expect(store.user).toEqual(authenticatedUser)
      expect(store.mustChangePassword).toBe(true)
      expect(store.canUsePrivateNavigation).toBe(false)
    },
  )
})
