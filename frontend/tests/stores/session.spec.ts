import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import type { ApiClient } from '@/api'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { useSessionStore } from '@/stores/session'

import { apiClientWithRoutes } from '../helpers/api'

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }

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
})

describe('useSessionStore.login', () => {
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
})

describe('useSessionStore.logout', () => {
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
})
