import { computed, watch } from 'vue'
import { useRoute, useRouter, type LocationQueryValue } from 'vue-router'

import { AGREEMENT_TIERS, CANONICAL_LABELS, WORKFLOW_STATES } from '@/composables/useVocabulary'
import type { components } from '@/api/schema'
import { QUEUES, type QueueId } from '@/components/domain/reviewQueues'

type AgreementTier = components['schemas']['AgreementTier']
type CanonicalLabel = components['schemas']['CanonicalLabel']
type PredictionStatus = components['schemas']['PredictionStatus']
type ReviewWorkflowState = components['schemas']['ReviewWorkflowState']

type ReviewSort = 'uncertainty' | 'tei_id'

const PREDICTION_STATUSES: readonly PredictionStatus[] = ['success', 'abstain', 'error']

export interface ReviewFilters {
  queue: QueueId
  q: string
  sort: ReviewSort
  workflowStates: ReviewWorkflowState[]
  finalLabel: CanonicalLabel | null
  agreementTiers: AgreementTier[]
  hasAuthorityConflict: boolean | null
  hasPredictionError: boolean | null
  methodName: string | null
  methodLabel: CanonicalLabel | null
  predictionStatus: PredictionStatus | null
}

const many = (value: LocationQueryValue | LocationQueryValue[] | undefined): string[] =>
  (Array.isArray(value) ? value : [value]).filter(
    (v): v is string => typeof v === 'string' && v !== '',
  )
const one = (value: LocationQueryValue | LocationQueryValue[] | undefined): string | null =>
  many(value)[0] ?? null
const oneOf = <T extends string>(value: string | null, allowed: readonly T[]): T | null =>
  allowed.find((candidate) => candidate === value) ?? null
const someOf = <T extends string>(values: string[], allowed: readonly T[]): T[] =>
  allowed.filter((candidate) => values.includes(candidate))
const bool = (value: string | null): boolean | null =>
  value === 'true' ? true : value === 'false' ? false : null

/**
 * The review screen's whole view state lives in the URL, so a queue, its filters and the selected
 * person can be bookmarked, shared and reached with the browser's back button (docs/23: stable deep
 * links). Unknown or malformed values are ignored rather than trusted.
 */
export function useReviewFilters(fixedQueue?: QueueId) {
  const route = useRoute()
  const router = useRouter()

  const filters = computed<ReviewFilters>(() => {
    const q = route.query
    // The register (people browser) is always the whole register: its queue is not a URL choice.
    const queue = fixedQueue ?? oneOf(one(q.queue), QUEUES) ?? 'contested'
    return {
      queue,
      q: one(q.q) ?? '',
      // The two queues default to the versioned triage order; the plain register defaults to TEI order.
      sort:
        oneOf(one(q.sort), ['uncertainty', 'tei_id'] as const) ??
        (queue === 'all' ? 'tei_id' : 'uncertainty'),
      workflowStates: someOf(many(q.state), WORKFLOW_STATES),
      finalLabel: oneOf(one(q.label), CANONICAL_LABELS),
      agreementTiers: someOf(many(q.agreement), AGREEMENT_TIERS),
      hasAuthorityConflict: bool(one(q.conflict)),
      hasPredictionError: bool(one(q.error)),
      methodName: one(q.method),
      methodLabel: oneOf(one(q.methodLabel), CANONICAL_LABELS),
      predictionStatus: oneOf(one(q.status), PREDICTION_STATUSES),
    }
  })

  const person = computed(() => one(route.query.person))

  // A navigation is asynchronous: two changes made before the first has landed in the route would
  // otherwise both start from the old URL and the second would erase the first. Until the route
  // catches up, the latest write is the state the next change builds on.
  let pending: { filters: ReviewFilters; person: string | null } | null = null
  watch(
    () => route.fullPath,
    () => {
      pending = null
    },
  )
  const currentFilters = (): ReviewFilters => pending?.filters ?? filters.value
  const currentPerson = (): string | null => (pending ? pending.person : person.value)

  function write(next: ReviewFilters, selected: string | null) {
    const requested = { filters: next, person: selected }
    pending = requested
    const query: Record<string, string | string[]> = {}
    if (!fixedQueue && next.queue !== 'contested') query.queue = next.queue
    if (next.q.trim() !== '') query.q = next.q.trim()
    const defaultSort = next.queue === 'all' ? 'tei_id' : 'uncertainty'
    if (next.sort !== defaultSort) query.sort = next.sort
    if (next.workflowStates.length > 0) query.state = next.workflowStates
    if (next.finalLabel) query.label = next.finalLabel
    if (next.agreementTiers.length > 0) query.agreement = next.agreementTiers
    if (next.hasAuthorityConflict !== null) query.conflict = String(next.hasAuthorityConflict)
    if (next.hasPredictionError !== null) query.error = String(next.hasPredictionError)
    if (next.methodName) query.method = next.methodName
    // method_label and prediction_status refine a method, so they only exist alongside one.
    if (next.methodName && next.methodLabel) query.methodLabel = next.methodLabel
    if (next.methodName && next.predictionStatus) query.status = next.predictionStatus
    if (selected) query.person = selected
    return router.replace({ query }).then((failure) => {
      if (failure && pending === requested) pending = null
      return failure
    })
  }

  /** Change filters; the selection is kept, so a filter never silently blanks the detail. */
  function setFilters(patch: Partial<ReviewFilters>): void {
    void write({ ...currentFilters(), ...patch }, currentPerson())
  }

  /** Switching queue starts that queue fresh: its own tiers, order and no leftover filters. */
  function setQueue(queue: QueueId): void {
    void write(
      {
        queue,
        q: '',
        sort: queue === 'all' ? 'tei_id' : 'uncertainty',
        workflowStates: [],
        finalLabel: null,
        agreementTiers: [],
        hasAuthorityConflict: null,
        hasPredictionError: null,
        methodName: null,
        methodLabel: null,
        predictionStatus: null,
      },
      null,
    )
  }

  function selectPerson(teiId: string | null) {
    return write(currentFilters(), teiId)
  }

  return { filters, person, setFilters, setQueue, selectPerson }
}
