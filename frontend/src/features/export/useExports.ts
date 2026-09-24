import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { usePolledQuery } from '@/composables/usePolledQuery'

export type ExportExecution = components['schemas']['ExportExecution']
export type ExportCreateRequest = components['schemas']['ExportCreateRequest']
export type ExportFormat = components['schemas']['ExportFormat']
export type LabelSourcePolicy = components['schemas']['LabelSourcePolicy']

const TERMINAL_STATUSES = new Set<ExportExecution['status']>(['completed', 'failed', 'cancelled'])
export const isTerminalExport = (item: ExportExecution): boolean =>
  TERMINAL_STATUSES.has(item.status)

const LIST_POLL_MS = 2000

export function exportListKey(runId: string) {
  return ['runs', runId, 'exports'] as const
}

/** `GET /runs/{run_id}/exports`, newest first in every lifecycle state, polled while one is live. */
export function useExportList(runId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()

  return useInfiniteQuery({
    queryKey: computed(() => exportListKey(runId.value)),
    queryFn: ({ pageParam }) =>
      unwrap(
        client.GET('/api/v1/runs/{run_id}/exports', {
          params: { path: { run_id: runId.value }, query: { cursor: pageParam } },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
    refetchInterval: (query) => {
      const pages = query.state.data?.pages ?? []
      const anyLive = pages.some((page) => page.items.some((item) => !isTerminalExport(item)))
      return anyLive ? LIST_POLL_MS : false
    },
    enabled,
  })
}

/** `GET /exports/{export_execution_id}`, polled until the export reaches an end state. */
export function useExport(exportId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()

  return usePolledQuery({
    queryKey: computed(() => ['exports', exportId.value] as const),
    queryFn: () =>
      unwrap(
        client.GET('/api/v1/exports/{export_execution_id}', {
          params: { path: { export_execution_id: exportId.value } },
        }),
      ),
    isTerminal: isTerminalExport,
    enabled,
  })
}

/** `POST /exports`: queue a durable export over one completed aggregation (`202`). */
export function useCreateExport() {
  const client = useApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    onSettled: (_created, _error, input) => {
      void queryClient.invalidateQueries({ queryKey: exportListKey(input.run_id) })
    },
    mutationFn: (input: ExportCreateRequest): Promise<ExportExecution> =>
      unwrap(client.POST('/api/v1/exports', { body: input })),
  })
}
