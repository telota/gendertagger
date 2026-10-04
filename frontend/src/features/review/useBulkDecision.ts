import { useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'

import { ApiError } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { annotationHistoryKey } from '@/composables/resourceQueries'
import { useSessionStore } from '@/stores/session'

import { invalidateAfterDecision, postAnnotation } from '@/composables/useAnnotate'
import type { components } from '@/api/schema'

type ReviewItem = components['schemas']['ReviewItem']
type CanonicalLabel = components['schemas']['CanonicalLabel']
type ReviewAction = components['schemas']['ReviewAction']

/** One decision applied to many people. `verify` uses each person's own machine label. */
export interface BulkSpec {
  action: ReviewAction
  /** For `correct`: the one label for everybody. Ignored for `verify` and `defer`. */
  label: CanonicalLabel | null
  comment: string
}

export type BulkOutcome =
  | { kind: 'saved'; revision: number }
  /** The person changed since the list was read; nothing was written for them. */
  | { kind: 'conflict'; currentRevision: number | null }
  /** Nothing to confirm: the machine reached no label for this person. */
  | { kind: 'skipped' }
  | { kind: 'forbidden' }
  | { kind: 'failed' }
  /** The reviewer stopped the run before this person's turn. */
  | { kind: 'notAttempted' }

export interface BulkResult {
  teiId: string
  outcome: BulkOutcome
}

export type BulkPhase = 'idle' | 'running' | 'done'

/**
 * Apply one decision to a selection as a *client-side sequence*: the backend has no batch endpoint,
 * and each annotation is its own append-only write against its own `expected_revision`, taken from
 * the list the reviewer was looking at. So one person's conflict says exactly that about that
 * person; it never blocks, retries or rolls back the others, and every person gets an explicit
 * outcome the reviewer can read afterwards.
 *
 * Writes go one after the other (never in parallel), in list order, so the report reads in the
 * order of the queue and the server is not flooded. A stop request takes effect before the next
 * person; the person in flight is never abandoned.
 */
export function useBulkDecision() {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const session = useSessionStore()

  const phase = ref<BulkPhase>('idle')
  const results = ref<BulkResult[]>([])
  const total = ref(0)
  const stopRequested = ref(false)

  const done = computed(() => results.value.length)
  watch(() => session.principalRevision, reset, { flush: 'sync' })

  async function run(items: readonly ReviewItem[], spec: BulkSpec): Promise<BulkResult[]> {
    const principalId = session.user?.id ?? null
    const revision = session.principalRevision
    const ownsRun = () =>
      (session.user?.id ?? null) === principalId && session.principalRevision === revision
    phase.value = 'running'
    results.value = []
    total.value = items.length
    stopRequested.value = false

    for (const item of items) {
      if (!ownsRun()) return []
      if (stopRequested.value) {
        results.value = [
          ...results.value,
          { teiId: item.tei_id, outcome: { kind: 'notAttempted' } },
        ]
        continue
      }
      const label = spec.action === 'verify' ? (item.machine_label ?? null) : spec.label
      if (spec.action !== 'defer' && label === null) {
        results.value = [...results.value, { teiId: item.tei_id, outcome: { kind: 'skipped' } }]
        continue
      }
      try {
        const annotation = await postAnnotation(client, {
          item,
          action: spec.action,
          label: spec.action === 'defer' ? null : label,
          comment: spec.comment,
          expectedRevision: item.review_revision,
        })
        if (!ownsRun()) return []
        results.value = [
          ...results.value,
          {
            teiId: item.tei_id,
            outcome: { kind: 'saved', revision: annotation.resulting_revision },
          },
        ]
      } catch (error) {
        if (!ownsRun()) return []
        results.value = [...results.value, { teiId: item.tei_id, outcome: failure(error) }]
      }
    }

    // One refresh at the end, not one per person: the queues and counts are re-read once.
    if (!ownsRun()) return []
    const [first] = items
    if (first) {
      invalidateAfterDecision(queryClient, { snapshotId: first.snapshot_id }, principalId)
      for (const item of items) {
        void queryClient.invalidateQueries({
          queryKey: annotationHistoryKey(item.snapshot_id, item.tei_id),
        })
      }
    }
    phase.value = 'done'
    return results.value
  }

  function failure(error: unknown): BulkOutcome {
    if (error instanceof ApiError) {
      if (error.code === 'annotation_conflict') {
        const current = error.details['current_revision']
        return { kind: 'conflict', currentRevision: typeof current === 'number' ? current : null }
      }
      if (error.code === 'forbidden') return { kind: 'forbidden' }
    }
    return { kind: 'failed' }
  }

  function stop(): void {
    stopRequested.value = true
  }

  function reset(): void {
    phase.value = 'idle'
    results.value = []
    total.value = 0
    stopRequested.value = false
  }

  return { phase, results, total, done, stopRequested, run, stop, reset }
}
