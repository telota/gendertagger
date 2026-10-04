import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { unwrap } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useSessionStore } from '@/stores/session'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import { currentData } from '@/composables/queryData'
import {
  importedSnapshotKey,
  importedPeopleKey,
  importedPersonKey,
  snapshotStatisticsKey,
} from '@/composables/resourceQueries'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'

const SNAPSHOT_POLL_INTERVAL_MS = 2000

/** Snapshot inspection is scoped to its project route and authenticated principal. */
export function useImportedSnapshot(
  projectId: Readonly<Ref<string>>,
  snapshotId: Readonly<Ref<string>>,
  enabled: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  const cache = useQueryClient()
  const session = useSessionStore()
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() =>
    importedSnapshotKey(session.user?.id, projectId.value, snapshotId.value),
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
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() =>
    snapshotStatisticsKey(session.user?.id, projectId.value, snapshotId.value),
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
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() => importedPeopleKey(session.user?.id, projectId.value, snapshotId.value))
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/people', {
          params: { path: { snapshot_id: queryKey[3] }, query: { cursor: pageParam } },
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
  const { canRead } = usePrivateQueryScope(() => enabled.value && teiId.value !== null)
  const key = computed(() =>
    importedPersonKey(session.user?.id, projectId.value, snapshotId.value, teiId.value),
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
