import { useQueryClient } from '@tanstack/vue-query'
import { watch } from 'vue'

import { useSessionStore } from '@/stores/session'

/** Destroy private reads and mutation results as soon as their authenticated owner changes. */
export function usePrivateCacheLifecycle(): void {
  const cache = useQueryClient()
  const session = useSessionStore()
  watch(
    () => session.principalRevision,
    () => {
      // Public branding is the only anonymous TanStack query. Anonymous classification owns its
      // capability state separately and is unaffected by private-session transitions.
      const privateQueries = {
        predicate: (query: { queryKey: readonly unknown[] }) => query.queryKey[0] !== 'branding',
      }
      void cache.cancelQueries(privateQueries)
      cache.removeQueries(privateQueries)
      cache.getMutationCache().clear()
    },
    { flush: 'sync' },
  )
}
