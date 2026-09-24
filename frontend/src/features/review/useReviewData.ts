import { useInfiniteQuery, useQuery } from '@tanstack/vue-query'
import { computed, ref, type Ref } from 'vue'

import { unwrap, type components, type paths } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

import { QUEUE_TIERS, type ReviewFilters } from './useReviewFilters'

export type ReviewItem = components['schemas']['ReviewItem']
export type ReviewSummary = components['schemas']['ReviewSummary']
export type ResultMethodPrediction = components['schemas']['ResultMethodPrediction']
export type AnnotationHistory = components['schemas']['AnnotationHistory']
export type AttributedAnnotation = components['schemas']['AttributedAnnotation']
export type PersonRecord = components['schemas']['PersonRecord']

const PAGE_SIZE = 50

type ReviewItemsQuery = NonNullable<paths['/api/v1/review-items']['get']['parameters']['query']>

/**
 * Everything the server needs except the cursor: the tuple a cursor is only valid for. Optional
 * parameters are left out rather than set to `undefined` (exactOptionalPropertyTypes), and
 * `method_label` / `prediction_status` are sent only with a `method_name`, as the server requires.
 */
function serverQuery(aggregationId: string, filters: ReviewFilters): ReviewItemsQuery {
  const query: ReviewItemsQuery = {
    aggregation_id: aggregationId,
    certainty_tiers: [...QUEUE_TIERS[filters.queue]],
    workflow_states: [...filters.workflowStates],
    agreement_tiers: [...filters.agreementTiers],
    sort: filters.sort,
    limit: PAGE_SIZE,
  }
  if (filters.finalLabel) query.final_label = filters.finalLabel
  if (filters.hasAuthorityConflict !== null)
    query.has_authority_conflict = filters.hasAuthorityConflict
  if (filters.hasPredictionError !== null) query.has_prediction_error = filters.hasPredictionError
  if (filters.methodName) {
    query.method_name = filters.methodName
    if (filters.methodLabel) query.method_label = filters.methodLabel
    if (filters.predictionStatus) query.prediction_status = filters.predictionStatus
  }
  if (filters.q.trim() !== '') query.q = filters.q.trim()
  return query
}

export function reviewItemsKey(aggregationId: string, filters: ReviewFilters) {
  return [
    'aggregations',
    aggregationId,
    'review-items',
    serverQuery(aggregationId, filters),
  ] as const
}

/**
 * `GET /review-items` with the complete server-side filter set and cursor pagination. The filter
 * tuple is part of the query key, so a new filter is a new list from its first page and a cursor
 * is never reused across tuples.
 */
export function useReviewItems(
  aggregationId: Ref<string>,
  filters: Ref<ReviewFilters>,
  enabled: Ref<boolean> = ref(true),
) {
  const client = useApiClient()

  return useInfiniteQuery({
    queryKey: computed(() => reviewItemsKey(aggregationId.value, filters.value)),
    queryFn: ({ pageParam }) =>
      unwrap(
        client.GET('/api/v1/review-items', {
          params: {
            query: {
              ...serverQuery(aggregationId.value, filters.value),
              ...(pageParam === null ? {} : { cursor: pageParam }),
            },
          },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
    enabled,
  })
}

/** `GET /aggregations/{id}/review-summary`: the counts behind the queue badges (never page counts). */
export function useReviewSummary(aggregationId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()

  return useQuery({
    queryKey: computed(() => ['aggregations', aggregationId.value, 'review-summary'] as const),
    queryFn: () =>
      unwrap(
        client.GET('/api/v1/aggregations/{aggregation_id}/review-summary', {
          params: { path: { aggregation_id: aggregationId.value } },
        }),
      ),
    enabled,
  })
}

/**
 * One item by its person id, for a deep link to somebody the current list does not (yet) contain.
 * `q` matches names and ids on the server; the exact `tei_id` is picked from its answer.
 */
export function useReviewItemByPerson(
  aggregationId: Ref<string>,
  teiId: Ref<string | null>,
  enabled: Ref<boolean>,
) {
  const client = useApiClient()

  return useQuery({
    queryKey: computed(
      () => ['aggregations', aggregationId.value, 'review-item', teiId.value] as const,
    ),
    queryFn: async () => {
      const id = teiId.value
      if (id === null) throw new Error('useReviewItemByPerson: no person.')
      const page = await unwrap(
        client.GET('/api/v1/review-items', {
          params: {
            query: { aggregation_id: aggregationId.value, q: id, sort: 'tei_id', limit: 20 },
          },
        }),
      )
      return page.items.find((item) => item.tei_id === teiId.value) ?? null
    },
    enabled: computed(() => enabled.value && teiId.value !== null),
  })
}

/** `GET /aggregations/{id}/results/{result_id}/predictions`, in the aggregation's selection order. */
export function useResultPredictions(aggregationId: Ref<string>, resultId: Ref<string | null>) {
  const client = useApiClient()

  return useQuery({
    queryKey: computed(
      () =>
        ['aggregations', aggregationId.value, 'results', resultId.value, 'predictions'] as const,
    ),
    queryFn: () => {
      const id = resultId.value
      if (id === null) throw new Error('useResultPredictions: no result selected.')
      return unwrap(
        client.GET('/api/v1/aggregations/{aggregation_id}/results/{result_id}/predictions', {
          params: { path: { aggregation_id: aggregationId.value, result_id: id } },
        }),
      )
    },
    enabled: computed(() => resultId.value !== null),
  })
}

export function annotationHistoryKey(snapshotId: string, teiId: string) {
  return ['snapshots', snapshotId, 'annotations', teiId] as const
}

/**
 * `GET /annotations`: one person's complete, attributed annotation chain, newest first. Its
 * `revision` is what the next decision must send as `expected_revision` (M5b).
 */
export function useAnnotationHistory(snapshotId: Ref<string | null>, teiId: Ref<string | null>) {
  const client = useApiClient()

  return useQuery({
    queryKey: computed(() => annotationHistoryKey(snapshotId.value ?? '', teiId.value ?? '')),
    queryFn: () => {
      const snapshot = snapshotId.value
      const tei = teiId.value
      if (snapshot === null || tei === null) throw new Error('useAnnotationHistory: no person.')
      return unwrap(
        client.GET('/api/v1/annotations', {
          params: { query: { snapshot_id: snapshot, tei_id: tei } },
        }),
      )
    },
    enabled: computed(() => snapshotId.value !== null && teiId.value !== null),
  })
}

/** `GET /snapshots/{id}/people/{tei_id}`: the source-preserving record behind a person. */
export function usePersonRecord(snapshotId: Ref<string | null>, teiId: Ref<string | null>) {
  const client = useApiClient()

  return useQuery({
    queryKey: computed(() => ['snapshots', snapshotId.value, 'people', teiId.value] as const),
    queryFn: () => {
      const snapshot = snapshotId.value
      const tei = teiId.value
      if (snapshot === null || tei === null) throw new Error('usePersonRecord: no person.')
      return unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}/people/{tei_id}', {
          params: { path: { snapshot_id: snapshot, tei_id: tei } },
        }),
      )
    },
    enabled: computed(() => snapshotId.value !== null && teiId.value !== null),
  })
}
