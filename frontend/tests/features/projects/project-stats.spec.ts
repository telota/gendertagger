import { describe, expect, it } from 'vitest'

import type { components } from '@/api'
import { reviewProgress, snapshotStats } from '@/features/projects/projectStats'
import type { DatasetSnapshot } from '@/features/projects/useSnapshotImport'
import { queueCounts } from '@/features/review/useReviewFilters'

type Group = components['schemas']['ReviewSummaryGroup']

function group(overrides: Partial<Group>): Group {
  return {
    agreement_tier: 'unanimous',
    certainty_tier: 'high',
    final_label: 'male',
    result_count: 1,
    review_action: null,
    workflow_state: 'unreviewed',
    ...overrides,
  }
}

function snapshot(status: DatasetSnapshot['status']): DatasetSnapshot {
  return {
    id: `snapshot-${status}`,
    project_id: 'project',
    status,
    created_at: '2026-01-01T00:00:00Z',
    parser_version: '1',
    source_artifact_id: 'artifact',
    source_sha256: 'sha',
  }
}

describe('snapshotStats', () => {
  it('counts lifecycle states and takes the first ready snapshot as the latest', () => {
    const stats = snapshotStats(
      [snapshot('pending'), snapshot('importing'), snapshot('ready'), snapshot('failed')],
      false,
    )

    expect(stats).toMatchObject({ loaded: 4, hasMore: false, inProgress: 2, failed: 1 })
    expect(stats.latestReady?.id).toBe('snapshot-ready')
  })

  it('has no latest ready snapshot when none has finished', () => {
    expect(snapshotStats([snapshot('importing')], true).latestReady).toBeNull()
  })
})

describe('reviewProgress', () => {
  it('folds workflow state, decisions, and final labels from the same groups', () => {
    const progress = reviewProgress([
      group({ result_count: 5 }),
      group({ result_count: 3, workflow_state: 'reviewed', review_action: 'verify' }),
      group({
        result_count: 2,
        final_label: 'female',
        workflow_state: 'reviewed',
        review_action: 'correct',
      }),
      group({
        result_count: 4,
        final_label: null,
        workflow_state: 'deferred',
        review_action: 'defer',
      }),
    ])

    expect(progress).toEqual({
      unreviewed: 5,
      reviewed: 5,
      deferred: 4,
      verified: 3,
      corrected: 2,
      labels: { male: 8, female: 2, unknown: 0, institution: 0 },
      // A person without any label stays apart from `unknown`, which is a label of its own.
      unlabelled: 4,
    })
  })

  it('is all zeros for no groups', () => {
    expect(reviewProgress([])).toMatchObject({ reviewed: 0, unlabelled: 0 })
  })
})

describe('queueCounts', () => {
  it('splits the evidence queues by certainty tier and counts only unreviewed people as open', () => {
    const counts = queueCounts([
      group({ certainty_tier: 'high', result_count: 50 }),
      group({ certainty_tier: 'contested', result_count: 10 }),
      group({ certainty_tier: 'low', result_count: 4, workflow_state: 'reviewed' }),
      group({ certainty_tier: 'single', result_count: 8 }),
      group({ certainty_tier: 'uncertain', result_count: 2, workflow_state: 'deferred' }),
    ])

    expect(counts.contested).toEqual({ total: 14, open: 10 })
    expect(counts.thin).toEqual({ total: 10, open: 8 })
    expect(counts.all).toEqual({ total: 74, open: 68 })
  })
})
