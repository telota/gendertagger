import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { ref, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { usePolledQuery } from '@/composables/usePolledQuery'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'

import type { MethodExecutionSummary } from './useRunDetail'

export type AggregationExecution = components['schemas']['AggregationExecution']
export type AggregationStrategy = components['schemas']['AggregationStrategy']

const TERMINAL_STATUSES = new Set<AggregationExecution['status']>([
  'completed',
  'failed',
  'cancelled',
])
export const isTerminalAggregation = (aggregation: AggregationExecution): boolean =>
  TERMINAL_STATUSES.has(aggregation.status)

/** Executions the backend accepts into an aggregation (`completed`, `completed_with_errors`). */
export const AGGREGATABLE_EXECUTION_STATUSES: ReadonlySet<MethodExecutionSummary['status']> =
  new Set(['completed', 'completed_with_errors'])

const LIST_POLL_MS = 2000

export function aggregationListKey(runId: string) {
  return ['runs', runId, 'aggregations'] as const
}

/**
 * `GET /runs/{run_id}/aggregations`, newest first in every lifecycle state, cursor-paginated. While
 * any listed aggregation is still queued or running the list re-reads itself, so a freshly created
 * one moves to its end state without a reload.
 */
export function useAggregationList(runId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => aggregationListKey(runId.value))

  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/runs/{run_id}/aggregations', {
          params: { path: { run_id: queryKey[1] }, query: { cursor: pageParam } },
          signal,
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
    refetchInterval: (query) => {
      const pages = query.state.data?.pages ?? []
      const anyLive = pages.some((page) => page.items.some((item) => !isTerminalAggregation(item)))
      return anyLive ? LIST_POLL_MS : false
    },
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

/** `GET /aggregations/{aggregation_id}`, polled until the aggregation reaches an end state. */
export function useAggregation(aggregationId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => ['aggregations', aggregationId.value] as const)

  const query = usePolledQuery({
    queryKey: key,
    queryFn: ({ signal }) =>
      unwrap(
        client.GET('/api/v1/aggregations/{aggregation_id}', {
          params: { path: { aggregation_id: aggregationId.value } },
          signal,
        }),
      ),
    isTerminal: isTerminalAggregation,
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

export interface AggregationCreateInput {
  runId: string
  /** In the order `GET /runs/{id}/executions` returns them: the server matches the exact order. */
  methodExecutionIds: readonly string[]
  strategy: AggregationStrategy
}

export interface AggregationCreated {
  aggregation: AggregationExecution
  /** `200`: an identical aggregation was already queued, running or completed (ADR-0034). */
  reused: boolean
}

/** `POST /runs/{run_id}/aggregations`; `409` means the selection is not aggregatable. */
export function useCreateAggregation() {
  const client = useApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    onSettled: (_created, _error, input) => {
      void queryClient.invalidateQueries({ queryKey: aggregationListKey(input.runId) })
    },
    mutationFn: async (input: AggregationCreateInput): Promise<AggregationCreated> => {
      let status = 0
      const aggregation = await unwrap<AggregationExecution>(
        client
          .POST('/api/v1/runs/{run_id}/aggregations', {
            params: { path: { run_id: input.runId } },
            body: {
              method_execution_ids: [...input.methodExecutionIds],
              strategy: input.strategy,
            },
          })
          .then((settled) => {
            status = settled.response.status
            return settled
          }),
      )
      return { aggregation, reused: status === 200 }
    },
  })
}
