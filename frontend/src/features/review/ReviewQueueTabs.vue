<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { QUEUES, type QueueCount, type QueueId } from './useReviewFilters'

defineProps<{
  queue: QueueId
  /** From `review-summary`, never counted from loaded pages. Null while it is not known. */
  counts: Record<QueueId, QueueCount> | null
}>()
const emit = defineEmits<{ select: [queue: QueueId] }>()

const { t, n } = useI18n()

function title(queue: QueueId): string {
  switch (queue) {
    case 'contested':
      return t('review.queue.contested.title')
    case 'thin':
      return t('review.queue.thin.title')
    case 'all':
      return t('review.queue.all.title')
  }
}

function hint(queue: QueueId): string {
  switch (queue) {
    case 'contested':
      return t('review.queue.contested.hint')
    case 'thin':
      return t('review.queue.thin.hint')
    case 'all':
      return t('review.queue.all.hint')
  }
}
</script>

<template>
  <div class="queues" role="group" :aria-label="t('review.queue.label')">
    <button
      v-for="id in QUEUES"
      :key="id"
      type="button"
      class="queue"
      :class="`queue--${id}`"
      :aria-pressed="queue === id"
      @click="emit('select', id)"
    >
      <span v-if="counts" class="queue-count">{{
        t('review.queue.count', {
          open: n(counts[id].open, 'integer'),
          total: n(counts[id].total, 'integer'),
        })
      }}</span>
      <span class="queue-title">{{ title(id) }}</span>
      <span class="queue-hint">{{ hint(id) }}</span>
    </button>
  </div>
</template>

<style scoped>
.queues {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.queue {
  display: flex;
  flex: 1 1 16rem;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.queue[aria-pressed='true'] {
  border-color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent);
}

.queue-count {
  align-self: flex-end;
  font-weight: var(--weight-semibold);
  font-variant-numeric: tabular-nums;
}

.queue-title {
  font-weight: var(--weight-semibold);
}

.queue-hint {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
</style>
