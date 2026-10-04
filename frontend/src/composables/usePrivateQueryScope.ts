import { useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter, type Ref } from 'vue'

import { currentData } from '@/composables/queryData'
import { privateQueryKey } from '@/composables/resourceQueries'
import { useSessionStore } from '@/stores/session'

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
    return computed(() =>
      currentData(cache, queryKey.value, canRead.value, query.status.value, query.data.value),
    )
  }

  return { canRead, key, data }
}
