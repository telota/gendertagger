import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import { currentData } from '@/composables/queryData'
import {
  projectDataAvailabilityKey,
  taskSnapshotsKey,
  taskRunsKey,
  taskResultsKey,
  projectReviewResultsKey,
  taskRunKey,
  workingSelectionKey,
} from '@/composables/resourceQueries'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'
import { useSessionStore } from '@/stores/session'

export type TaskMode = 'classification' | 'review' | 'annotation' | 'game'
export type Snapshot = components['schemas']['DatasetSnapshot']

/** Data facts are independent of selected resources and isolated by principal/project. */
export function useProjectDataAvailability(projectId: Ref<string>, enabled: Ref<boolean>) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() => projectDataAvailabilityKey(session.user?.id, projectId.value))
  const query = useQuery({
    queryKey: key,
    queryFn: async ({ queryKey, signal }) => {
      const availability = await unwrap(
        client.GET('/api/v1/projects/{project_id}/data-availability', {
          params: { path: { project_id: queryKey[2] } },
          signal,
        }),
      )
      if (availability.project_id !== queryKey[2])
        throw new Error('Project availability belongs to a different project.')
      return availability
    },
    enabled: canRead,
    staleTime: 1000,
    // Imports and aggregations finish in workers, including ones started in another browser.
    refetchInterval: 5000,
  })
  const data = computed(() =>
    query.isSuccess.value
      ? currentData(cache, key.value, canRead.value, query.status.value, query.data.value)
      : undefined,
  )
  return { ...query, data }
}

export function useTaskSnapshots(
  projectId: Ref<string>,
  resultsOnly: Ref<boolean>,
  enabled: Ref<boolean>,
) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() => taskSnapshotsKey(session.user?.id, projectId.value, resultsOnly.value))
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}/snapshots', {
          params: {
            path: { project_id: queryKey[2] },
            query: {
              status: 'ready',
              ...(queryKey[3] ? { has_completed_aggregations: true } : {}),
              limit: 25,
              cursor: pageParam,
            },
          },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled: canRead,
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}

export function useTaskRuns(snapshotId: Ref<string>, enabled: Ref<boolean>) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() => taskRunsKey(session.user?.id, snapshotId.value))
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/runs', {
          params: {
            path: { snapshot_id: queryKey[2] },
            query: { has_completed_aggregations: true, limit: 25, cursor: pageParam },
          },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled: canRead,
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}

export function useTaskResults(runId: Ref<string>, enabled: Ref<boolean>) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() => taskResultsKey(session.user?.id, runId.value))
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/runs/{run_id}/aggregations', {
          params: {
            path: { run_id: queryKey[2] },
            query: { status: 'completed', limit: 25, cursor: pageParam },
          },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled: canRead,
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}

export function useProjectReviewResults(projectId: Ref<string>, enabled: Ref<boolean>) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() => projectReviewResultsKey(session.user?.id, projectId.value))
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}/review-results', {
          params: {
            path: { project_id: queryKey[2] },
            query: { limit: 25, cursor: pageParam },
          },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled: canRead,
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}

export function useTaskRun(
  projectId: Ref<string>,
  snapshotId: Ref<string>,
  runId: Ref<string>,
  enabled: Ref<boolean>,
) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() =>
    taskRunKey(session.user?.id, projectId.value, snapshotId.value, runId.value),
  )
  const query = useQuery({
    queryKey: key,
    queryFn: async ({ queryKey, signal }) => {
      const run = await unwrap(
        client.GET('/api/v1/runs/{run_id}', { params: { path: { run_id: queryKey[4] } }, signal }),
      )
      return run.id === queryKey[4] && run.dataset_snapshot_id === queryKey[3] ? run : null
    },
    enabled: canRead,
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}

/** Resolve only the explicit recommendation; this performs reads and never selects or creates data. */
export function useWorkingSelection(
  projectId: Ref<string>,
  aggregationId: Ref<string | null>,
  enabled: Ref<boolean>,
) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(() => enabled.value && aggregationId.value !== null)
  const key = computed(() =>
    workingSelectionKey(session.user?.id, projectId.value, aggregationId.value),
  )
  const query = useQuery({
    queryKey: key,
    queryFn: async ({ queryKey, signal }) => {
      if (queryKey[3] === null) return null
      const aggregation = await unwrap(
        client.GET('/api/v1/aggregations/{aggregation_id}', {
          params: { path: { aggregation_id: queryKey[3] } },
          signal,
        }),
      )
      if (aggregation.id !== queryKey[3] || aggregation.status !== 'completed') return null
      const run = await unwrap(
        client.GET('/api/v1/runs/{run_id}', {
          params: { path: { run_id: aggregation.run_id } },
          signal,
        }),
      )
      if (run.id !== aggregation.run_id) return null
      const snapshot = await unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}', {
          params: { path: { snapshot_id: run.dataset_snapshot_id } },
          signal,
        }),
      )
      return snapshot.id === run.dataset_snapshot_id &&
        snapshot.project_id === queryKey[2] &&
        snapshot.status === 'ready'
        ? { snapshotId: snapshot.id, runId: run.id, aggregationId: aggregation.id }
        : null
    },
    enabled: canRead,
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}
