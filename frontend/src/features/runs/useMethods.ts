import { useQuery } from '@tanstack/vue-query'
import { ref, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

export type MethodDescriptor = components['schemas']['MethodDescriptor']

// The roster changes only with a server deployment, so a short-lived cache is plenty.
const ROSTER_STALE_MS = 5 * 60 * 1000

/**
 * `GET /methods`: the methods this server can run, in the order the server lists them. The client
 * never hardcodes a roster (docs/23: the wireframe's list was wrong on both counts).
 */
export function useMethodList(enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()

  return useQuery({
    queryKey: ['methods'] as const,
    queryFn: () => unwrap(client.GET('/api/v1/methods')),
    staleTime: ROSTER_STALE_MS,
    enabled,
  })
}
