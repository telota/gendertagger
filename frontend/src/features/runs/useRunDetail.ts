import { useQuery } from '@tanstack/vue-query'
import { ref, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'

import type { Run } from './useRuns'

export type MethodExecutionSummary = components['schemas']['MethodExecutionSummary']

/** No further state change can follow: the stream is closed and nothing needs polling. */
export const TERMINAL_RUN_STATUSES: ReadonlySet<Run['status']> = new Set([
  'completed',
  'completed_with_errors',
  'failed',
  'cancelled',
])

export const TERMINAL_METHOD_EXECUTION_STATUSES: ReadonlySet<MethodExecutionSummary['status']> =
  new Set(['completed', 'completed_with_errors', 'failed', 'cancelled'])

export function runKey(runId: string) {
  return ['runs', runId] as const
}

export function runExecutionsKey(runId: string) {
  return ['runs', runId, 'executions'] as const
}

/** `GET /runs/{run_id}`: the persisted run, which is authoritative over anything streamed. */
export function useRun(runId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => runKey(runId.value))

  const query = useQuery({
    queryKey: key,
    queryFn: ({ queryKey, signal }) =>
      unwrap(
        client.GET('/api/v1/runs/{run_id}', { params: { path: { run_id: queryKey[1] } }, signal }),
      ),
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

/** `GET /runs/{run_id}/executions`: every method execution of the run, in the server's stable order. */
export function useRunExecutions(runId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => runExecutionsKey(runId.value))

  const query = useQuery({
    queryKey: key,
    queryFn: ({ queryKey, signal }) =>
      unwrap(
        client.GET('/api/v1/runs/{run_id}/executions', {
          params: { path: { run_id: queryKey[1] } },
          signal,
        }),
      ),
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}
