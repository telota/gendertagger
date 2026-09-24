import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { unwrap, type components } from '@/api'
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
 *
 * On success everything that derives from the decision is refetched (the person's chain, every
 * queue, the counts on the queue cards), so the final-decision view changes while the machine
 * result it is derived from is untouched.
 */
export function useCreateAnnotation() {
  const client = useApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: DecisionInput): Promise<Annotation> => {
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
    },
    onSettled: (_annotation, error, input) => {
      const aggregationId = input.item.aggregation_execution_id
      // A conflict means the person changed: the chain must be re-read either way.
      void queryClient.invalidateQueries({
        queryKey: annotationHistoryKey(input.item.snapshot_id, input.item.tei_id),
      })
      if (error) return
      for (const part of ['review-items', 'review-summary', 'review-item']) {
        void queryClient.invalidateQueries({ queryKey: ['aggregations', aggregationId, part] })
      }
    },
  })
}
