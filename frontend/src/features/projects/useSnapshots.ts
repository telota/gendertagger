import { useInfiniteQuery, useQuery } from '@tanstack/vue-query'
import { computed, ref, type Ref } from 'vue'

import { unwrap } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

/** Shared with the import mutation so a new upload refreshes the list it will appear in. */
export function snapshotListKey(projectId: string) {
  return ['projects', projectId, 'snapshots'] as const
}

/**
 * `GET /projects/{project_id}/snapshots`, newest first in every lifecycle state, cursor-paginated
 * (docs/23: server-side order, never re-sorted in the browser).
 */
export function useSnapshotList(projectId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()

  return useInfiniteQuery({
    queryKey: computed(() => snapshotListKey(projectId.value)),
    queryFn: ({ pageParam }) =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}/snapshots', {
          params: { path: { project_id: projectId.value }, query: { cursor: pageParam } },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
    enabled,
  })
}

/** `GET /snapshots/{snapshot_id}/source-members`, fetched only once a caller asks for it. */
export function useSnapshotSourceMembers(snapshotId: Ref<string>, enabled: Ref<boolean>) {
  const client = useApiClient()

  return useQuery({
    queryKey: computed(() => ['snapshots', snapshotId.value, 'source-members'] as const),
    queryFn: () =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/source-members', {
          params: { path: { snapshot_id: snapshotId.value } },
        }),
      ),
    enabled,
  })
}
