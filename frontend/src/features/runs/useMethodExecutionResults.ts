import { useInfiniteQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import { methodExecutionResultsKey } from '@/composables/resourceQueries'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'
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
  const { canRead } = usePrivateQueryScope(enabled)
  const queryText = computed(() => search.value.trim())
  const key = computed(() =>
    methodExecutionResultsKey(
      session.user?.id,
      runId.value,
      methodExecutionId.value,
      queryText.value,
    ),
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
    ...cursorQueryOptions,
    enabled: canRead,
  })
}
