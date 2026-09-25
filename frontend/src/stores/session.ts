import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError, unwrap, type components } from '@/api'
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
  // Navigation waits for both login responses without unmounting a recovery caller's unsaved form.
  const isAuthenticating = ref(false)
  /**
   * `idle` before the first `initialize()`, `loading` while it runs, `ready` once it resolves
   * either signed in or ordinarily signed out, `error` if the server itself could not be reached
   * or failed — a distinct state, since treating that as "signed out" would tell a viewer to sign
   * in when the real problem is the server (M2 exit criterion: a server error renders correctly).
   */
  const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')

  const isSignedIn = computed(() => user.value !== null)
  const canUsePrivateNavigation = computed(
    () =>
      status.value === 'ready' &&
      isSignedIn.value &&
      !mustChangePassword.value &&
      !isAuthenticating.value,
  )

  /** Resolve the current session from the browser's cookie, if any. Call once at app start. */
  async function initialize(): Promise<void> {
    status.value = 'loading'
    try {
      user.value = await unwrap(client.GET('/api/v1/me'))
      await refreshSessionFlags()
      status.value = 'ready'
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        // No valid session is the ordinary signed-out state, not a failure to surface.
        user.value = null
        mustChangePassword.value = false
        status.value = 'ready'
      } else {
        status.value = 'error'
      }
    }
  }

  async function refreshSessionFlags(): Promise<void> {
    const session = await unwrap(client.GET('/api/v1/auth/session'))
    mustChangePassword.value = session.must_change_password
  }

  /** Throws `ApiError` (e.g. `invalid_credentials`) for the caller to display. */
  async function login(credentials: LoginCredentials): Promise<void> {
    isAuthenticating.value = true
    try {
      const authenticatedUser = await unwrap(
        client.POST('/api/v1/auth/login', {
          body: {
            username: credentials.username,
            password: credentials.password,
            keep_signed_in: credentials.keepSignedIn,
          },
        }),
      )
      try {
        await refreshSessionFlags()
      } catch (error) {
        status.value = 'error'
        throw error
      }
      user.value = authenticatedUser
      status.value = 'ready'
    } finally {
      isAuthenticating.value = false
    }
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
    isAuthenticating,
    status,
    isSignedIn,
    canUsePrivateNavigation,
    initialize,
    login,
    logout,
    forgetSession,
    changePassword,
  }
})
