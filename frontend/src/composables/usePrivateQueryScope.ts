import { useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter, type Ref } from 'vue'

import { ApiError } from '@/api'
import { useSessionStore } from '@/stores/session'

/** Append the principal without changing resource prefixes used for invalidation. */
export function privateQueryKey<T extends readonly unknown[]>(
  resourceKey: T,
  principalId: string | null | undefined,
) {
  return [...resourceKey, { principal_id: principalId ?? null }] as const
}

/** Private reads are eligible only after authentication and forced-change checks finish. */
export function usePrivateQueryScope(enabled: MaybeRefOrGetter<boolean> = true) {
  const session = useSessionStore()
  const cache = useQueryClient()
  const canRead = computed(() => toValue(enabled) && session.canUsePrivateNavigation)

  function key<T extends readonly unknown[]>(resourceKey: () => T) {
    return computed(() => privateQueryKey(resourceKey(), session.user?.id))
  }

  function data<T>(
    query: { status: Ref<string>; data: Ref<T | undefined> },
    queryKey: Ref<readonly unknown[]>,
  ) {
    return computed(() => {
      // Observers can lag a synchronous account switch. Resolve the current owner's exact key.
      if (!canRead.value || query.status.value === 'pending' || query.data.value === undefined)
        return undefined
      const state = cache.getQueryState<T>(queryKey.value)
      if (state?.error instanceof ApiError && [401, 403, 404].includes(state.error.status ?? 0))
        return undefined
      return state?.data
    })
  }

  return { canRead, key, data }
}
