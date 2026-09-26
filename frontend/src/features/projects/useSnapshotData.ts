import { useInfiniteQuery, useQuery, useQueryClient, type QueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { ApiError, unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useSessionStore } from '@/stores/session'

export type ImportedPerson = components['schemas']['PersonRecord']
export type SnapshotStatistics = components['schemas']['DatasetSnapshotStatistics']

const SNAPSHOT_POLL_INTERVAL_MS = 2000

/** Resolve the exact current cache key before rendering; an observer can lag a route/account change. */
export function currentData<T>(
  client: QueryClient,
  key: readonly unknown[],
  enabled: boolean,
  status: string,
  observed: T | undefined,
): T | undefined {
  if (!enabled || status === 'pending' || observed === undefined) return undefined
  const state = client.getQueryState<T>(key)
  const error = state?.error
  if (error instanceof ApiError && error.status !== null && [401, 403, 404].includes(error.status))
    return undefined
  return state?.data
}

/** Snapshot inspection is scoped to its project route and authenticated principal. */
export function useImportedSnapshot(
  projectId: Readonly<Ref<string>>,
  snapshotId: Readonly<Ref<string>>,
  enabled: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  const cache = useQueryClient()
  const session = useSessionStore()
  const canRead = computed(() => enabled.value && session.canUsePrivateNavigation)
  const key = computed(
    () => ['imported-snapshot', session.user?.id, projectId.value, snapshotId.value] as const,
  )
  const query = useQuery({
    queryKey: key,
    queryFn: ({ queryKey, signal }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}', {
          params: { path: { snapshot_id: queryKey[3] } },
          signal,
        }),
      ),
    enabled: canRead,
    // The detail view and navigation can subscribe after one another. Share an active import's
    // current polling interval instead of issuing a second immediate read; settled/error states
    // still revalidate when revisited, and explicit invalidation bypasses this freshness window.
    staleTime: (state) => {
      const snapshot = state.state.data
      return state.state.status === 'success' &&
        snapshot?.id === snapshotId.value &&
        snapshot.project_id === projectId.value &&
        ['pending', 'importing'].includes(snapshot.status)
        ? SNAPSHOT_POLL_INTERVAL_MS
        : 0
    },
    refetchInterval: (state) => {
      const snapshot = state.state.data
      return state.state.status !== 'error' &&
        snapshot?.id === snapshotId.value &&
        snapshot.project_id === projectId.value &&
        ['pending', 'importing'].includes(snapshot.status)
        ? SNAPSHOT_POLL_INTERVAL_MS
        : false
    },
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}

/** Materialized source-inventory statistics are immutable once a snapshot is ready. */
export function useSnapshotStatistics(
  projectId: Readonly<Ref<string>>,
  snapshotId: Readonly<Ref<string>>,
  enabled: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  const cache = useQueryClient()
  const session = useSessionStore()
  const canRead = computed(() => enabled.value && session.canUsePrivateNavigation)
  const key = computed(
    () => ['snapshot-statistics', session.user?.id, projectId.value, snapshotId.value] as const,
  )
  const query = useQuery({
    queryKey: key,
    queryFn: ({ queryKey, signal }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/statistics', {
          params: { path: { snapshot_id: queryKey[3] } },
          signal,
        }),
      ),
    enabled: canRead,
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}

/** Raw immutable records use the server's TEI-ID order; no partial-list search or sorting. */
export function useImportedPeople(
  projectId: Readonly<Ref<string>>,
  snapshotId: Readonly<Ref<string>>,
  enabled: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  const cache = useQueryClient()
  const session = useSessionStore()
  const canRead = computed(() => enabled.value && session.canUsePrivateNavigation)
  const key = computed(
    () => ['imported-people', session.user?.id, projectId.value, snapshotId.value] as const,
  )
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/people', {
          params: { path: { snapshot_id: queryKey[3] }, query: { cursor: pageParam } },
          signal,
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => (page.has_more ? (page.next_cursor ?? null) : undefined),
    enabled: canRead,
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}

/** Exact record lookup supports a deep-linked selection outside the loaded collection pages. */
export function useImportedPerson(
  projectId: Readonly<Ref<string>>,
  snapshotId: Readonly<Ref<string>>,
  teiId: Readonly<Ref<string | null>>,
  enabled: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  const cache = useQueryClient()
  const session = useSessionStore()
  const canRead = computed(
    () => enabled.value && session.canUsePrivateNavigation && teiId.value !== null,
  )
  const key = computed(
    () =>
      [
        'imported-person',
        session.user?.id,
        projectId.value,
        snapshotId.value,
        teiId.value,
      ] as const,
  )
  const query = useQuery({
    queryKey: key,
    queryFn: ({ queryKey, signal }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/people/{tei_id}', {
          params: { path: { snapshot_id: queryKey[3], tei_id: queryKey[4] ?? '' } },
          signal,
        }),
      ),
    enabled: canRead,
  })
  const data = computed(() =>
    currentData(cache, key.value, canRead.value, query.status.value, query.data.value),
  )
  return { ...query, data }
}
