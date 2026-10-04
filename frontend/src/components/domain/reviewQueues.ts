import type { components } from '@/api/schema'

type CertaintyTier = components['schemas']['CertaintyTier']

/**
 * D2: the two review buckets are distinct and must not be merged into one "below a threshold"
 * list. Each is one `GET /review-items` query; `all` is the plain register traversal.
 */
export type QueueId = 'contested' | 'thin' | 'all'

/** Counts behind one queue card: everything in it, and what is still unreviewed. */
export interface QueueCount {
  total: number
  open: number
}

export const QUEUES: readonly QueueId[] = ['contested', 'thin', 'all']
export const QUEUE_TIERS: Record<QueueId, readonly CertaintyTier[]> = {
  contested: ['low', 'contested'],
  thin: ['single', 'uncertain'],
  all: [],
}

/**
 * Every queue's counts from the `review-summary` groups, never from loaded pages. One definition for
 * the queue cards and any other screen that quotes "open of total", so the numbers cannot drift.
 */
export function queueCounts(
  groups: readonly components['schemas']['ReviewSummaryGroup'][],
): Record<QueueId, QueueCount> {
  const result = {} as Record<QueueId, QueueCount>
  for (const queue of QUEUES) {
    const tiers = QUEUE_TIERS[queue]
    const inQueue = groups.filter(
      (group) => tiers.length === 0 || tiers.includes(group.certainty_tier),
    )
    result[queue] = {
      total: inQueue.reduce((sum, group) => sum + group.result_count, 0),
      open: inQueue
        .filter((group) => group.workflow_state === 'unreviewed')
        .reduce((sum, group) => sum + group.result_count, 0),
    }
  }
  return result
}
