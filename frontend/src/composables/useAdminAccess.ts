import { computed } from 'vue'

import { useSessionStore } from '@/stores/session'

export type AdminAccessState =
  'loading' | 'sessionError' | 'signedOut' | 'passwordChangeRequired' | 'forbidden' | 'eligible'

/**
 * The shared, client-side administrative eligibility presentation. The backend remains the
 * authorization authority; this prevents exposing or fetching private administrative state early.
 */
export function useAdminAccess() {
  const session = useSessionStore()

  const state = computed<AdminAccessState>(() => {
    if (session.status === 'idle' || session.status === 'loading' || session.isAuthenticating)
      return 'loading'
    if (session.status === 'error') return 'sessionError'
    if (!session.isSignedIn) return 'signedOut'
    if (session.mustChangePassword) return 'passwordChangeRequired'
    return session.user?.roles?.includes('admin') ? 'eligible' : 'forbidden'
  })

  const canAccessAdmin = computed(() => state.value === 'eligible')

  return { state, canAccessAdmin, session }
}
