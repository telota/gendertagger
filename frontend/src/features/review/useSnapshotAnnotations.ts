import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { currentData } from '@/features/projects/useSnapshotData'
import { useSessionStore } from '@/stores/session'
import type { CanonicalLabel, ReviewWorkflowState } from './useVocabulary'

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
  const canRead = computed(() => enabled.value && session.canUsePrivateNavigation)
  const filtersQuery = computed(() => ({
    ...(filters.value.q.trim() ? { q: filters.value.q.trim() } : {}),
    workflow_states: filters.value.workflowState ? [filters.value.workflowState] : [],
    ...(filters.value.humanLabel ? { human_label: filters.value.humanLabel } : {}),
    limit: 50,
  }))
  const key = computed(
    () =>
      [
        'snapshot-annotation-items',
        snapshotId.value,
        session.user?.id,
        filtersQuery.value,
      ] as const,
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
    initialPageParam: null as string | null,
    getNextPageParam: (page) => (page.has_more ? page.next_cursor : undefined),
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
  const canRead = computed(
    () => enabled.value && session.canUsePrivateNavigation && teiId.value !== '',
  )
  const key = computed(
    () => ['snapshot-annotation-item', snapshotId.value, session.user?.id, teiId.value] as const,
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
