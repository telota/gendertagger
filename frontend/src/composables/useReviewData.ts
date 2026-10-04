import { useQuery } from '@tanstack/vue-query'
import { ref, type Ref } from 'vue'

import { unwrap } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'
import {
  annotationHistoryKey,
  reviewItemKey,
  reviewSummaryKey,
  resultPredictionsKey,
  personRecordKey,
} from '@/composables/resourceQueries'

/** `GET /aggregations/{id}/review-summary`: the counts behind the queue badges (never page counts). */
export function useReviewSummary(aggregationId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()

  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => reviewSummaryKey(aggregationId.value))
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) =>
      unwrap(
        client.GET('/api/v1/aggregations/{aggregation_id}/review-summary', {
          params: { path: { aggregation_id: aggregationId.value } },
          signal,
        }),
      ),
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

/**
 * One item by its person id, for a deep link to somebody the current list does not (yet) contain.
 * Exact server-side identity filtering avoids looking for an ID in the first fuzzy-search page.
 */
export function useReviewItemByPerson(
  aggregationId: Ref<string>,
  teiId: Ref<string | null>,
  enabled: Ref<boolean>,
) {
  const client = useApiClient()

  const scope = usePrivateQueryScope(() => enabled.value && teiId.value !== null)
  const key = scope.key(() => reviewItemKey(aggregationId.value, teiId.value))
  const query = useQuery({
    queryKey: key,
    queryFn: async ({ queryKey, signal }) => {
      const id = queryKey[3]
      if (id === null) throw new Error('useReviewItemByPerson: no person.')
      const page = await unwrap(
        client.GET('/api/v1/review-items', {
          params: {
            query: { aggregation_id: queryKey[1], tei_id: id, sort: 'tei_id', limit: 1 },
          },
          signal,
        }),
      )
      return page.items.find((item) => item.tei_id === id) ?? null
    },
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

/** `GET /aggregations/{id}/results/{result_id}/predictions`, in the aggregation's selection order. */
export function useResultPredictions(aggregationId: Ref<string>, resultId: Ref<string | null>) {
  const client = useApiClient()

  const scope = usePrivateQueryScope(() => resultId.value !== null)
  const key = scope.key(() => resultPredictionsKey(aggregationId.value, resultId.value))
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => {
      const id = resultId.value
      if (id === null) throw new Error('useResultPredictions: no result selected.')
      return unwrap(
        client.GET('/api/v1/aggregations/{aggregation_id}/results/{result_id}/predictions', {
          params: { path: { aggregation_id: aggregationId.value, result_id: id } },
          signal,
        }),
      )
    },
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

/**
 * `GET /annotations`: one person's complete, attributed annotation chain, newest first. Its
 * `revision` is what the next decision must send as `expected_revision` (M5b).
 */
export function useAnnotationHistory(snapshotId: Ref<string | null>, teiId: Ref<string | null>) {
  const client = useApiClient()

  const scope = usePrivateQueryScope(() => snapshotId.value !== null && teiId.value !== null)
  const key = scope.key(() => annotationHistoryKey(snapshotId.value ?? '', teiId.value ?? ''))
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => {
      const snapshot = snapshotId.value
      const tei = teiId.value
      if (snapshot === null || tei === null) throw new Error('useAnnotationHistory: no person.')
      return unwrap(
        client.GET('/api/v1/annotations', {
          params: { query: { snapshot_id: snapshot, tei_id: tei } },
          signal,
        }),
      )
    },
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}

/** `GET /snapshots/{id}/people/{tei_id}`: the source-preserving record behind a person. */
export function usePersonRecord(snapshotId: Ref<string | null>, teiId: Ref<string | null>) {
  const client = useApiClient()

  const scope = usePrivateQueryScope(() => snapshotId.value !== null && teiId.value !== null)
  const key = scope.key(() => personRecordKey(snapshotId.value, teiId.value))
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => {
      const snapshot = snapshotId.value
      const tei = teiId.value
      if (snapshot === null || tei === null) throw new Error('usePersonRecord: no person.')
      return unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/people/{tei_id}', {
          params: { path: { snapshot_id: snapshot, tei_id: tei } },
          signal,
        }),
      )
    },
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}
