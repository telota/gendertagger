import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { ref, type Ref } from 'vue'

import { unwrap } from '@/api'
import type { components } from '@/api/schema'
import { useApiClient } from '@/composables/useApiClient'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'
import { useSessionStore } from '@/stores/session'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import { runListKey } from '@/composables/resourceQueries'

type RunConfig = components['schemas']['RunConfig']

/** `GET /snapshots/{snapshot_id}/runs`, newest first in every lifecycle state, cursor-paginated. */
export function useRunList(snapshotId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => runListKey(snapshotId.value))

  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ pageParam, signal, queryKey }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/runs', {
          params: { path: { snapshot_id: queryKey[1] }, query: { cursor: pageParam } },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

export interface RunCreateInput {
  snapshotId: string
  config: RunConfig
}

/**
 * Create a run and schedule it. The backend splits this in two commands (`POST /runs` persists the
 * validated run, `POST /runs/{id}/executions` atomically persists its executions and dispatch
 * intents); to the operator it is one action. If scheduling fails the run stays `created` and shows
 * up in the list, so the failure is visible rather than lost.
 */
export function useCreateRun() {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const session = useSessionStore()

  return useMutation({
    onSettled: (_run, _error, input) => {
      void queryClient.invalidateQueries({ queryKey: runListKey(input.snapshotId) })
    },
    mutationFn: async (input: RunCreateInput) => {
      const principal = session.user?.id ?? null
      const revision = session.principalRevision
      const created = await unwrap(
        client.POST('/api/v1/runs', {
          body: { dataset_snapshot_id: input.snapshotId, config: input.config },
        }),
      )
      // The follow-up command belongs to the account that created the run, including A -> B -> A.
      if ((session.user?.id ?? null) !== principal || session.principalRevision !== revision)
        throw new DOMException('Stale account', 'AbortError')
      return unwrap(
        client.POST('/api/v1/runs/{run_id}/executions', {
          params: { path: { run_id: created.id } },
        }),
      )
    },
  })
}
