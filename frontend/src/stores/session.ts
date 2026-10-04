import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

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
  // Replacing or forgetting an account invalidates ownership even if it is later signed in again.
  // Reauthentication as the same account preserves request/draft ownership.
  const principalRevision = ref(0)
  watch(
    () => user.value?.id ?? null,
    (principal, previous) => {
      if (principal !== previous) principalRevision.value += 1
    },
    { flush: 'sync' },
  )
  const mustChangePassword = ref(false)
  // Navigation waits for both login responses without unmounting a recovery caller's unsaved form.
  const isAuthenticating = ref(false)
  let authenticationGeneration = 0
  let sessionResolutionGeneration = 0
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
    if (isAuthenticating.value) return
    const generation = ++sessionResolutionGeneration
    let revision = principalRevision.value
    const stillOwnsResolution = () =>
      generation === sessionResolutionGeneration && revision === principalRevision.value
    status.value = 'loading'
    try {
      const currentUser = await unwrap(client.GET('/api/v1/me'))
      if (!stillOwnsResolution()) return
      user.value = currentUser
      revision = principalRevision.value
      const flags = await readSessionFlags()
      if (!stillOwnsResolution()) return
      mustChangePassword.value = flags.must_change_password
      status.value = 'ready'
    } catch (error) {
      if (!stillOwnsResolution()) return
      if (error instanceof ApiError && error.status === 401) {
        // No valid session is the ordinary signed-out state, not a failure to surface.
        forgetSession()
        status.value = 'ready'
      } else {
        status.value = 'error'
      }
    }
  }

  async function readSessionFlags() {
    return unwrap(client.GET('/api/v1/auth/session'))
  }

  /** Throws `ApiError` (e.g. `invalid_credentials`) for the caller to display. */
  async function login(credentials: LoginCredentials): Promise<void> {
    const generation = ++sessionResolutionGeneration
    let revision = principalRevision.value
    const assertOwnsResolution = () => {
      if (generation !== sessionResolutionGeneration || revision !== principalRevision.value)
        throw new DOMException('The session resolution was superseded.', 'AbortError')
    }
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
      assertOwnsResolution()
      authenticationGeneration += 1
      // The server cookie already belongs to this principal. Publish it before the flags request,
      // including when that request fails, so old private ownership cannot survive replacement.
      user.value = authenticatedUser
      revision = principalRevision.value
      try {
        const flags = await readSessionFlags()
        assertOwnsResolution()
        mustChangePassword.value = flags.must_change_password
      } catch (error) {
        if (generation === sessionResolutionGeneration && revision === principalRevision.value)
          status.value = 'error'
        throw error
      }
      status.value = 'ready'
    } finally {
      if (generation === sessionResolutionGeneration) isAuthenticating.value = false
    }
  }

  /** Clear the local session state only, without a server round trip. */
  function forgetSession(): void {
    sessionResolutionGeneration += 1
    user.value = null
    mustChangePassword.value = false
    isAuthenticating.value = false
    status.value = 'ready'
  }

  /** Return true only when the response ends the session that began this logout request. */
  async function logout(): Promise<boolean> {
    // Reauthentication can replace a session without changing its account ID. A read-only refresh
    // of the same account, however, still belongs to this logout request.
    const principalId = user.value?.id ?? null
    const revision = principalRevision.value
    const generation = authenticationGeneration
    const stillOwnsSession = () =>
      (user.value?.id ?? null) === principalId &&
      principalRevision.value === revision &&
      authenticationGeneration === generation &&
      !isAuthenticating.value
    try {
      await unwrap(client.POST('/api/v1/auth/logout'))
    } catch (error) {
      if (!stillOwnsSession()) return false
      // The endpoint requires an authenticated session, so 401 already means signed out.
      // Network/server failures leave the outcome unknown and must remain visible to the caller.
      if (!(error instanceof ApiError && error.status === 401)) throw error
    }
    if (!stillOwnsSession()) return false
    forgetSession()
    status.value = 'ready'
    return true
  }

  /** Throws `ApiError` (e.g. `invalid_current_password`) for the caller to display. */
  async function changePassword(payload: ChangePasswordPayload): Promise<void> {
    const revision = principalRevision.value
    await unwrap(
      client.POST('/api/v1/me/password', {
        body: {
          current_password: payload.currentPassword,
          new_password: payload.newPassword,
        },
      }),
    )
    if (revision !== principalRevision.value)
      throw new DOMException('The password change belongs to an obsolete session.', 'AbortError')
    mustChangePassword.value = false
  }

  return {
    user,
    principalRevision,
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
