import { computed, ref, type Ref } from 'vue'

import { QUEUE_TIERS } from '@/components/domain/reviewQueues'
import type { ReviewItemsQuery } from '@/composables/resourceQueries'
import { useReviewItemsQuery } from '@/composables/useReviewItemsQuery'

import type { ReviewFilters } from './useReviewFilters'

const PAGE_SIZE = 50

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

/** Project the review screen's queue/filter policy into the native resource reader. */
export function useReviewItems(
  aggregationId: Ref<string>,
  filters: Ref<ReviewFilters>,
  enabled: Ref<boolean> = ref(true),
) {
  return useReviewItemsQuery(
    computed(() => serverQuery(aggregationId.value, filters.value)),
    enabled,
  )
}
