import { useMutation, useQueryClient, type QueryClient } from '@tanstack/vue-query'

import { ApiError, unwrap, type ApiClient, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { privateQueryKey } from '@/composables/usePrivateQueryScope'
import type { AggregationExecution } from '@/features/runs/useAggregations'
import type { Run } from '@/features/runs/useRuns'
import { useSessionStore } from '@/stores/session'

import { annotationHistoryKey, type ReviewItem } from './useReviewData'
import type { CanonicalLabel, ReviewAction } from './useVocabulary'

export type Annotation = components['schemas']['Annotation']

/** A snapshot/person is sufficient; a classification result is optional supporting evidence. */
export type AnnotationTarget = Pick<
  components['schemas']['AnnotationCreate'],
  'snapshot_id' | 'tei_id' | 'aggregated_result_id'
>

export interface DecisionInput {
  item: AnnotationTarget
  action: ReviewAction
  /** Required for `verify` and `correct`, forbidden for `defer` (the server enforces the same). */
  label: CanonicalLabel | null
  comment: string
  /** The revision the reviewer saw; the server rejects the write if the person has moved on. */
  expectedRevision: number
}

/**
 * `POST /annotations`: append one decision. Never an update: a correction supersedes the earlier
 * annotation on the server, and a write against a stale `expected_revision` fails with
 * `409 annotation_conflict` instead of overwriting somebody else's decision.
 */
export function postAnnotation(client: ApiClient, input: DecisionInput): Promise<Annotation> {
  const comment = input.comment.trim()
  return unwrap(
    client.POST('/api/v1/annotations', {
      body: {
        snapshot_id: input.item.snapshot_id,
        tei_id: input.item.tei_id,
        action: input.action,
        ...(input.item.aggregated_result_id == null
          ? {}
          : { aggregated_result_id: input.item.aggregated_result_id }),
        expected_revision: input.expectedRevision,
        ...(input.label ? { label: input.label } : {}),
        ...(comment === '' ? {} : { comment }),
      },
    }),
  )
}

function belongsToPrincipal(queryKey: readonly unknown[], principalId: string | null): boolean {
  const owner = queryKey.at(-1)
  return (
    typeof owner === 'object' &&
    owner !== null &&
    'principal_id' in owner &&
    owner.principal_id === principalId
  )
}

/** Read known ownership without additional requests or assumptions about partially loaded pages. */
function cachedAggregationSnapshot(
  queryClient: QueryClient,
  aggregationId: string,
  principalId: string | null,
): string | null {
  const aggregation = queryClient.getQueryData<AggregationExecution>(
    privateQueryKey(['aggregations', aggregationId], principalId),
  )
  if (aggregation) {
    const run = queryClient.getQueryData<Run>(
      privateQueryKey(['runs', aggregation.run_id], principalId),
    )
    if (run) return run.dataset_snapshot_id
  }
  for (const [, item] of queryClient.getQueriesData<ReviewItem | null>({
    queryKey: ['aggregations', aggregationId, 'review-item'],
    predicate: (query) => belongsToPrincipal(query.queryKey, principalId),
  })) {
    if (item) return item.snapshot_id
  }
  for (const [, list] of queryClient.getQueriesData<{ pages: { items: ReviewItem[] }[] }>({
    queryKey: ['aggregations', aggregationId, 'review-items'],
    predicate: (query) => belongsToPrincipal(query.queryKey, principalId),
  })) {
    const item = list?.pages.find((page) => page.items.length > 0)?.items[0]
    if (item) return item.snapshot_id
  }
  return null
}

/** Decisions belong to a snapshot/person and affect every aggregation of that snapshot. */
export function invalidateAfterDecision(
  queryClient: QueryClient,
  scope: { snapshotId: string; teiId?: string },
  principalId: string | null,
): void {
  for (const resource of ['snapshot-annotation-items', 'snapshot-annotation-item']) {
    void queryClient.invalidateQueries({ queryKey: [resource, scope.snapshotId] })
  }
  if (scope.teiId !== undefined) {
    void queryClient.invalidateQueries({
      queryKey: annotationHistoryKey(scope.snapshotId, scope.teiId),
    })
  }
  const snapshots = new Map<string, string | null>()
  void queryClient.invalidateQueries({
    predicate: (query) => {
      const [resource, aggregationId, part] = query.queryKey
      if (
        resource !== 'aggregations' ||
        typeof aggregationId !== 'string' ||
        !['review-items', 'review-summary', 'review-item'].includes(String(part)) ||
        !belongsToPrincipal(query.queryKey, principalId)
      )
        return false
      if (!snapshots.has(aggregationId))
        snapshots.set(
          aggregationId,
          cachedAggregationSnapshot(queryClient, aggregationId, principalId),
        )
      const snapshotId = snapshots.get(aggregationId)
      // A summary or empty queue may outlive its ownership metadata. Refresh it conservatively:
      // an unknown scope is not proof that the decision cannot affect this projection.
      return snapshotId === null || snapshotId === scope.snapshotId
    },
  })
}

/**
 * One decision from the detail column. On success everything that derives from it is refetched (the
 * person's chain, every queue, the counts on the queue cards), so the final-decision view changes
 * while the machine result it is derived from is untouched.
 */
export function useCreateAnnotation() {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const session = useSessionStore()

  return useMutation({
    mutationFn: (input: DecisionInput): Promise<Annotation> => postAnnotation(client, input),
    onSettled: (_annotation, error, input) => {
      const scope = {
        snapshotId: input.item.snapshot_id,
        teiId: input.item.tei_id,
      }
      if (error && !(error instanceof ApiError && error.code === 'annotation_conflict')) {
        void queryClient.invalidateQueries({
          queryKey: annotationHistoryKey(scope.snapshotId, scope.teiId),
        })
        return
      }
      // A conflict also proves another decision changed the snapshot's projections.
      invalidateAfterDecision(queryClient, scope, session.user?.id ?? null)
    },
  })
}
