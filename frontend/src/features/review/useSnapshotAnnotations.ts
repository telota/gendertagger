import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { unwrap } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import { currentData } from '@/composables/queryData'
import {
  snapshotAnnotationItemsKey,
  snapshotAnnotationItemKey,
} from '@/composables/resourceQueries'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'
import { useSessionStore } from '@/stores/session'
import type { components } from '@/api/schema'

type CanonicalLabel = components['schemas']['CanonicalLabel']
type ReviewWorkflowState = components['schemas']['ReviewWorkflowState']

export type SnapshotAnnotationItem = components['schemas']['SnapshotAnnotationItem']
export interface SnapshotAnnotationFilters {
  q: string
  workflowState: ReviewWorkflowState | null
  humanLabel: CanonicalLabel | null
}

export function useSnapshotAnnotationItems(
  snapshotId: Ref<string>,
  filters: Ref<SnapshotAnnotationFilters>,
  enabled: Ref<boolean>,
) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(enabled)
  const filtersQuery = computed(() => ({
    ...(filters.value.q.trim() ? { q: filters.value.q.trim() } : {}),
    workflow_states: filters.value.workflowState ? [filters.value.workflowState] : [],
    ...(filters.value.humanLabel ? { human_label: filters.value.humanLabel } : {}),
    limit: 50,
  }))
  const key = computed(() =>
    snapshotAnnotationItemsKey(snapshotId.value, session.user?.id, filtersQuery.value),
  )
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/annotation-items', {
          params: {
            path: { snapshot_id: queryKey[1] },
            query: { ...queryKey[3], cursor: pageParam },
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

export function useSnapshotAnnotationItem(
  snapshotId: Ref<string>,
  teiId: Ref<string>,
  enabled: Ref<boolean>,
) {
  const client = useApiClient()
  const session = useSessionStore()
  const cache = useQueryClient()
  const { canRead } = usePrivateQueryScope(() => enabled.value && teiId.value !== '')
  const key = computed(() =>
    snapshotAnnotationItemKey(snapshotId.value, session.user?.id, teiId.value),
  )
  const query = useQuery({
    queryKey: key,
    queryFn: ({ queryKey, signal }) =>
      unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/annotation-items/{tei_id}', {
          params: { path: { snapshot_id: queryKey[1], tei_id: queryKey[3] } },
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
