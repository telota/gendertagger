import { useQuery } from '@tanstack/vue-query'
import { ref, type Ref } from 'vue'

import { unwrap } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'

// The roster changes only with a server deployment, so a short-lived cache is plenty.
const ROSTER_STALE_MS = 5 * 60 * 1000

/**
 * `GET /methods`: the methods this server can run, in the order the server lists them. The client
 * never hardcodes a roster (docs/23: the wireframe's list was wrong on both counts).
 */
export function useMethodList(enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => ['methods'] as const)

  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => unwrap(client.GET('/api/v1/methods', { signal })),
    staleTime: ROSTER_STALE_MS,
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}
