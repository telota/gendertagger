import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useSessionStore } from '@/stores/session'

/**
 * The per-view signed-out rule shared by every authenticated screen: wait for the one
 * loading -> ready transition of `session.initialize()` (still pending on every fresh page load,
 * cookie or not), and only then send a signed-out visitor to `/login?redirect=`. A server or
 * network failure is `status === 'error'`, never signed-out, and is retried with `retrySession`.
 */
export function useRequireSession() {
  const route = useRoute()
  const router = useRouter()
  const session = useSessionStore()

  watch(
    () => session.status,
    (status) => {
      if (status === 'ready' && !session.isSignedIn) {
        void router.replace({ name: 'login', query: { redirect: route.fullPath } })
      }
    },
    { immediate: true },
  )

  const isSignedIn = computed(() => session.status === 'ready' && session.isSignedIn)

  function retrySession(): void {
    void session.initialize()
  }

  return { session, isSignedIn, retrySession }
}

/** A single, non-repeating path segment is a plain string at runtime; the router types it wider. */
export function useRouteParam(name: string) {
  const route = useRoute()
  return computed(() => {
    const raw = route.params[name]
    return Array.isArray(raw) ? (raw[0] ?? '') : (raw ?? '')
  })
}
