import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ref, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { usePolledQuery } from '@/composables/usePolledQuery'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'

export type ExportExecution = components['schemas']['ExportExecution']
export type ExportCreateRequest = components['schemas']['ExportCreateRequest']
export type ExportFormat = components['schemas']['ExportFormat']
export type LabelSourcePolicy = components['schemas']['LabelSourcePolicy']
export type ExportManifestRecord = components['schemas']['ExportManifest']

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
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => exportListKey(runId.value))

  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/runs/{run_id}/exports', {
          params: { path: { run_id: queryKey[1] }, query: { cursor: pageParam } },
          signal,
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
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

/** `GET /exports/{export_execution_id}`, polled until the export reaches an end state. */
export function useExport(exportId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => ['exports', exportId.value] as const)

  const query = usePolledQuery({
    queryKey: key,
    queryFn: ({ signal }) =>
      unwrap(
        client.GET('/api/v1/exports/{export_execution_id}', {
          params: { path: { export_execution_id: exportId.value } },
          signal,
        }),
      ),
    isTerminal: isTerminalExport,
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
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

/**
 * `GET /exports/{id}/manifest`: the persisted provenance of a completed export (source snapshot
 * checksum and one checksummed descriptor per output), for every format. It is immutable once the
 * export is completed.
 */
export function useExportManifest(exportId: Ref<string>, enabled: Ref<boolean>) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => ['exports', exportId.value, 'manifest'] as const)

  const query = useQuery({
    queryKey: key,
    queryFn: ({ queryKey, signal }) =>
      unwrap(
        client.GET('/api/v1/exports/{export_execution_id}/manifest', {
          params: { path: { export_execution_id: queryKey[1] } },
          signal,
        }),
      ),
    staleTime: Infinity,
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}
