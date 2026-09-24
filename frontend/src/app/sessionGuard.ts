import type { Router } from 'vue-router'

import { requestReauthentication } from '@/composables/useSessionRecovery'
import { useSessionStore } from '@/stores/session'

// The login and logout requests handle their own failures inline (LoginView; a logout that itself
// 401s has nothing left to recover); intercepting them would show a sign-in prompt on top of a
// sign-in form, or on top of an action that already meant to end the session.
const PATHS_EXEMPT_FROM_RECOVERY = ['/api/v1/auth/login', '/api/v1/auth/logout']

/**
 * Administrative writes never replay after session recovery. A recovered session can belong to another
 * administrator, so retrying would execute the old actor's action under a different principal.
 */
export function shouldRetryAfterUnauthorized(request: Request): boolean {
  const { pathname } = new URL(request.url)
  const isAccountCreate = request.method === 'POST' && pathname.endsWith('/api/v1/admin/users')
  const isAccountUpdate =
    request.method === 'PATCH' && /\/api\/v1\/admin\/users\/[^/]+$/.test(pathname)
  const isSettingsUpdate = request.method === 'PATCH' && pathname.endsWith('/api/v1/admin/settings')
  const isSettingsReset =
    request.method === 'POST' && pathname.endsWith('/api/v1/admin/settings/reset')
  return !isAccountCreate && !isAccountUpdate && !isSettingsUpdate && !isSettingsReset
}

/**
 * Build the API client's `onUnauthorized` hook (decision D1): recover a session that expired mid-use
 * inline, without navigating away from the caller's page, and fall back to routing to `/login` —
 * preserving the page the user was on — if they decline.
 */
export function createUnauthorizedHandler(router: Router): (request: Request) => Promise<void> {
  return async (request) => {
    const path = new URL(request.url).pathname
    if (PATHS_EXEMPT_FROM_RECOVERY.some((exempt) => path.endsWith(exempt))) {
      throw new Error(`${path} handles its own 401s.`)
    }

    const session = useSessionStore()
    // Not yet known to be signed in (still resolving at boot, or already signed out): an ordinary
    // signed-out response, not a session that expired mid-use, so the calling view's own guard handles it.
    if (!session.isSignedIn) throw new Error('No signed-in session to recover.')

    try {
      await requestReauthentication()
    } catch (declined) {
      session.forgetSession()
      const current = router.currentRoute.value
      if (current.name !== 'login') {
        await router.push({ name: 'login', query: { redirect: current.fullPath } })
      }
      throw declined
    }
  }
}
