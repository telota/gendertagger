import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useSessionStore } from '@/stores/session'
import { cursorQueryOptions, liveListPolling } from '@/composables/cursorQuery'

import { currentData } from '@/composables/queryData'
import { snapshotListQueryKey, snapshotSourceMembersKey } from '@/composables/resourceQueries'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'

/** Newest first in every lifecycle state, with the server's opaque cursor and order. */
export function useSnapshotList(projectId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const session = useSessionStore()

  return useInfiniteQuery({
    queryKey: computed(() => snapshotListQueryKey(projectId.value, session.user?.id)),
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}/snapshots', {
          params: { path: { project_id: queryKey[1] }, query: { cursor: pageParam } },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled: computed(() => enabled.value && session.canUsePrivateNavigation),
    refetchInterval: liveListPolling<components['schemas']['CursorPage_DatasetSnapshot_']>({
      isLive: (snapshot) => ['pending', 'importing'].includes(snapshot.status),
      intervalMs: 5000,
      stopOnError: true,
    }),
  })
}

/** Source provenance is fetched on demand and never shared between principals. */
export function useSnapshotSourceMembers(snapshotId: Ref<string>, enabled: Ref<boolean>) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(enabled)
  const key = computed(() => snapshotSourceMembersKey(snapshotId.value, session.user?.id))
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
