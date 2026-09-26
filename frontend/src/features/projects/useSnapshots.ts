import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, type Ref } from 'vue'

import { unwrap } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useSessionStore } from '@/stores/session'

import { currentData } from './useSnapshotData'

/** Prefix shared with import invalidation; individual reads are isolated by principal. */
export function snapshotListKey(projectId: string) {
  return ['projects', projectId, 'snapshots'] as const
}

/** Newest first in every lifecycle state, with the server's opaque cursor and order. */
export function useSnapshotList(projectId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const session = useSessionStore()

  return useInfiniteQuery({
    queryKey: computed(
      () => [...snapshotListKey(projectId.value), session.user?.id ?? 'anonymous'] as const,
    ),
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}/snapshots', {
          params: { path: { project_id: queryKey[1] }, query: { cursor: pageParam } },
          signal,
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
    enabled: computed(() => enabled.value && session.canUsePrivateNavigation),
    refetchInterval: (query) =>
      query.state.status !== 'error' &&
      query.state.data?.pages.some((page) =>
        page.items.some((snapshot) => ['pending', 'importing'].includes(snapshot.status)),
      )
        ? 5000
        : false,
  })
}

/** Source provenance is fetched on demand and never shared between principals. */
export function useSnapshotSourceMembers(snapshotId: Ref<string>, enabled: Ref<boolean>) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const canRead = computed(() => enabled.value && session.canUsePrivateNavigation)
  const key = computed(
    () =>
      ['snapshots', snapshotId.value, 'source-members', session.user?.id ?? 'anonymous'] as const,
  )
  const query = useQuery({
    queryKey: key,
    queryFn: ({ queryKey, signal }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/source-members', {
          params: { path: { snapshot_id: queryKey[1] } },
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
