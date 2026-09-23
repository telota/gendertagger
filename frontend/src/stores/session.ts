import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

export type CurrentUser = components['schemas']['CurrentUser']

export interface LoginCredentials {
  username: string
  password: string
  keepSignedIn: boolean
}

export interface ChangePasswordPayload {
  currentPassword: string
  newPassword: string
}

/**
 * The signed-in principal and session state (ADR-0031, ADR-0032).
 *
 * Session and roles are exactly the "genuinely shared client state" docs/26-frontend-coding-guidelines.md
 * assigns to Pinia; they are not server-state-cache data, since there is exactly one session per running
 * client and every part of the shell needs to read it synchronously.
 */
export const useSessionStore = defineStore('session', () => {
  const client = useApiClient()

  const user = ref<CurrentUser | null>(null)
  const mustChangePassword = ref(false)
  /** `idle` before the first `initialize()`, `loading` while it runs, `ready` once resolved either way. */
  const status = ref<'idle' | 'loading' | 'ready'>('idle')

  const isSignedIn = computed(() => user.value !== null)

  /** Resolve the current session from the browser's cookie, if any. Call once at app start. */
  async function initialize(): Promise<void> {
    status.value = 'loading'
    try {
      user.value = await unwrap(client.GET('/api/v1/me'))
      await refreshSessionFlags()
    } catch {
      // No valid session is the ordinary signed-out state, not a failure to surface.
      user.value = null
      mustChangePassword.value = false
    } finally {
      status.value = 'ready'
    }
  }

  async function refreshSessionFlags(): Promise<void> {
    const session = await unwrap(client.GET('/api/v1/auth/session'))
    mustChangePassword.value = session.must_change_password
  }

  /** Throws `ApiError` (e.g. `invalid_credentials`) for the caller to display. */
  async function login(credentials: LoginCredentials): Promise<void> {
    user.value = await unwrap(
      client.POST('/api/v1/auth/login', {
        body: {
          username: credentials.username,
          password: credentials.password,
          keep_signed_in: credentials.keepSignedIn,
        },
      }),
    )
    await refreshSessionFlags()
  }

  /** Clear the local session state only, without a server round trip. */
  function forgetSession(): void {
    user.value = null
    mustChangePassword.value = false
  }

  async function logout(): Promise<void> {
    try {
      await unwrap(client.POST('/api/v1/auth/logout'))
    } finally {
      forgetSession()
    }
  }

  /** Throws `ApiError` (e.g. `invalid_current_password`) for the caller to display. */
  async function changePassword(payload: ChangePasswordPayload): Promise<void> {
    await unwrap(
      client.POST('/api/v1/me/password', {
        body: {
          current_password: payload.currentPassword,
          new_password: payload.newPassword,
        },
      }),
    )
    mustChangePassword.value = false
  }

  return {
    user,
    mustChangePassword,
    status,
    isSignedIn,
    initialize,
    login,
    logout,
    forgetSession,
    changePassword,
  }
})
