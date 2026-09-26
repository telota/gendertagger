import { useInfiniteQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useSessionStore } from '@/stores/session'

export type MethodExecutionResult = components['schemas']['MethodExecutionResult']

/**
 * Read one method's immutable outputs in the snapshot's TEI order. The server owns filtering and
 * cursor pagination so a partial browser list is never sorted or searched locally.
 */
export function useMethodExecutionResults(
  runId: Ref<string>,
  methodExecutionId: Ref<string>,
  search: Ref<string>,
  enabled: Ref<boolean>,
) {
  const client = useApiClient()
  const session = useSessionStore()
  const canRead = computed(() => enabled.value && session.canUsePrivateNavigation)
  const queryText = computed(() => search.value.trim())
  const key = computed(
    () =>
      [
        'method-execution-results',
        session.user?.id ?? 'anonymous',
        runId.value,
        methodExecutionId.value,
        queryText.value,
      ] as const,
  )

  return useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/runs/{run_id}/executions/{method_execution_id}/results', {
          params: {
            path: { run_id: queryKey[2], method_execution_id: queryKey[3] },
            query: {
              limit: 50,
              ...(queryKey[4] ? { q: queryKey[4] } : {}),
              cursor: pageParam,
            },
          },
          signal,
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => (page.has_more ? (page.next_cursor ?? null) : undefined),
    enabled: canRead,
  })
}
