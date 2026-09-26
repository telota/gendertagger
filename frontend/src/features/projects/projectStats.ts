import type { components } from '@/api'

import { CANONICAL_LABELS, type CanonicalLabel } from '../review/useVocabulary'
import type { DatasetSnapshot } from './useSnapshotImport'

type ReviewSummaryGroup = components['schemas']['ReviewSummaryGroup']

export interface SnapshotStats {
  /** Snapshots on the first page; only a lower bound while `hasMore`. */
  loaded: number
  hasMore: boolean
  inProgress: number
  failed: number
  /** The list is newest first, so the first ready snapshot is the latest one. */
  latestReady: DatasetSnapshot | null
}

export function snapshotStats(items: readonly DatasetSnapshot[], hasMore: boolean): SnapshotStats {
  return {
    loaded: items.length,
    hasMore,
    inProgress: items.filter(
      (snapshot) => snapshot.status === 'pending' || snapshot.status === 'importing',
    ).length,
    failed: items.filter((snapshot) => snapshot.status === 'failed').length,
    latestReady: items.find((snapshot) => snapshot.status === 'ready') ?? null,
  }
}

export interface ReviewProgress {
  unreviewed: number
  reviewed: number
  deferred: number
  /** Of the reviewed people, how many decisions confirmed the machine label ... */
  verified: number
  /** ... and how many replaced it. */
  corrected: number
  /** `final_label`: the latest human decision, otherwise the machine label (the export policy). */
  labels: Record<CanonicalLabel, number>
  /** People whose aggregation produced no label and whom nobody has labelled. */
  unlabelled: number
}

/** Fold the server's `review-summary` groups into the figures the project overview quotes. */
export function reviewProgress(groups: readonly ReviewSummaryGroup[]): ReviewProgress {
  const progress: ReviewProgress = {
    unreviewed: 0,
    reviewed: 0,
    deferred: 0,
    verified: 0,
    corrected: 0,
    labels: Object.fromEntries(CANONICAL_LABELS.map((label) => [label, 0])) as Record<
      CanonicalLabel,
      number
    >,
    unlabelled: 0,
  }
  for (const group of groups) {
    progress[group.workflow_state] += group.result_count
    if (group.review_action === 'verify') progress.verified += group.result_count
    if (group.review_action === 'correct') progress.corrected += group.result_count
    if (group.final_label) progress.labels[group.final_label] += group.result_count
    else progress.unlabelled += group.result_count
  }
  return progress
}
