import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ref, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { usePolledQuery } from '@/composables/usePolledQuery'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'

import { parseEvaluationReport } from './reportSchema'

export type EvaluationExecution = components['schemas']['EvaluationExecution']
export type EvaluationCreateRequest = components['schemas']['EvaluationCreateRequest']

const TERMINAL_STATUSES = new Set<EvaluationExecution['status']>([
  'completed',
  'failed',
  'cancelled',
])
export const isTerminalEvaluation = (evaluation: EvaluationExecution): boolean =>
  TERMINAL_STATUSES.has(evaluation.status)

const LIST_POLL_MS = 2000

export function evaluationListKey(runId: string) {
  return ['runs', runId, 'evaluations'] as const
}

/**
 * `GET /runs/{run_id}/evaluations`, newest first in every lifecycle state, cursor-paginated. While
 * one is still queued or running the list re-reads itself.
 */
export function useEvaluationList(runId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => evaluationListKey(runId.value))

  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/runs/{run_id}/evaluations', {
          params: { path: { run_id: queryKey[1] }, query: { cursor: pageParam } },
          signal,
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
    refetchInterval: (query) => {
      const pages = query.state.data?.pages ?? []
      const anyLive = pages.some((page) => page.items.some((item) => !isTerminalEvaluation(item)))
      return anyLive ? LIST_POLL_MS : false
    },
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

/** `GET /evaluations/{evaluation_id}`, polled until the evaluation reaches an end state. */
export function useEvaluation(evaluationId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => ['evaluations', evaluationId.value] as const)

  const query = usePolledQuery({
    queryKey: key,
    queryFn: ({ signal }) =>
      unwrap(
        client.GET('/api/v1/evaluations/{evaluation_id}', {
          params: { path: { evaluation_id: evaluationId.value } },
          signal,
        }),
      ),
    isTerminal: isTerminalEvaluation,
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

/**
 * `POST /evaluations`: queue an evaluation over exact, completed method executions. The server
 * accepts only the selection its definition prescribes and answers `409` for any other.
 */
export function useCreateEvaluation() {
  const client = useApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    onSettled: (_created, _error, input) => {
      void queryClient.invalidateQueries({ queryKey: evaluationListKey(input.run_id) })
    },
    mutationFn: (input: EvaluationCreateRequest): Promise<EvaluationExecution> =>
      unwrap(client.POST('/api/v1/evaluations', { body: input })),
  })
}

/**
 * `GET /evaluations/{id}/report` of a completed evaluation: the stored report, validated. The
 * response is untyped in OpenAPI, so a body of the wrong shape becomes an error, not a bad table.
 */
export function useEvaluationReport(evaluationId: Ref<string>, enabled: Ref<boolean>) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => ['evaluations', evaluationId.value, 'report'] as const)

  const query = useQuery({
    queryKey: key,
    queryFn: async ({ queryKey, signal }) => {
      const body: unknown = await unwrap(
        client.GET('/api/v1/evaluations/{evaluation_id}/report', {
          params: { path: { evaluation_id: queryKey[1] } },
          signal,
        }),
      )
      return parseEvaluationReport(body)
    },
    // A report is immutable once stored.
    staleTime: Infinity,
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}
