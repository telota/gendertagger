import { useMutation, useQueryClient, type QueryClient } from '@tanstack/vue-query'

import { unwrap, type ApiClient, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

import { annotationHistoryKey, type ReviewItem } from './useReviewData'
import type { CanonicalLabel, ReviewAction } from './useVocabulary'

export type Annotation = components['schemas']['Annotation']

export interface DecisionInput {
  item: ReviewItem
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
        aggregated_result_id: input.item.aggregated_result_id,
        expected_revision: input.expectedRevision,
        ...(input.label ? { label: input.label } : {}),
        ...(comment === '' ? {} : { comment }),
      },
    }),
  )
}

/** Refetch everything that derives from decisions: the queues, their counts and one person's chain. */
export function invalidateAfterDecision(
  queryClient: QueryClient,
  aggregationId: string,
  chain?: { snapshotId: string; teiId: string },
): void {
  if (chain) {
    void queryClient.invalidateQueries({
      queryKey: annotationHistoryKey(chain.snapshotId, chain.teiId),
    })
  }
  for (const part of ['review-items', 'review-summary', 'review-item']) {
    void queryClient.invalidateQueries({ queryKey: ['aggregations', aggregationId, part] })
  }
}

/**
 * One decision from the detail column. On success everything that derives from it is refetched (the
 * person's chain, every queue, the counts on the queue cards), so the final-decision view changes
 * while the machine result it is derived from is untouched.
 */
export function useCreateAnnotation() {
  const client = useApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: DecisionInput): Promise<Annotation> => postAnnotation(client, input),
    onSettled: (_annotation, error, input) => {
      const chain = { snapshotId: input.item.snapshot_id, teiId: input.item.tei_id }
      if (error) {
        // A conflict means the person changed: the chain must be re-read either way.
        void queryClient.invalidateQueries({
          queryKey: annotationHistoryKey(chain.snapshotId, chain.teiId),
        })
        return
      }
      invalidateAfterDecision(queryClient, input.item.aggregation_execution_id, chain)
    },
  })
}
