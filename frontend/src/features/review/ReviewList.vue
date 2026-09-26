<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'

import { reviewItemName } from './reviewItemName'
import type { ReviewItem } from './useReviewData'
import type { CertaintyTier } from './useVocabulary'
import VocabBadge from './VocabBadge.vue'

defineProps<{
  items: readonly ReviewItem[]
  selected: string | null
  loading: boolean
  failed: boolean
  hasMore: boolean
  loadingMore: boolean
  /** Whether the person may decide (reviewer or up): only then rows can be ticked for a bulk decision. */
  selectable: boolean
  ticked: ReadonlySet<string>
}>()
const emit = defineEmits<{
  select: [teiId: string]
  toggle: [teiId: string, checked: boolean]
  loadMore: []
  retry: []
}>()

const { t } = useI18n()
const list = ref<HTMLUListElement | null>(null)

// Contested evidence and thin evidence keep the colours the queue cards use.
const toneOf = (tier: CertaintyTier): 'contested' | 'low' | 'thin' | 'neutral' => {
  if (tier === 'contested') return 'contested'
  if (tier === 'low') return 'low'
  if (tier === 'single' || tier === 'uncertain') return 'thin'
  return 'neutral'
}

// Arrow keys move between rows (the rows are ordinary buttons, so Tab and Enter work as well).
function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  const rows = Array.from(list.value?.querySelectorAll<HTMLButtonElement>('button.row') ?? [])
  const index = rows.indexOf(document.activeElement as HTMLButtonElement)
  if (index === -1) return
  const next = rows[index + (event.key === 'ArrowDown' ? 1 : -1)]
  if (next) {
    event.preventDefault()
    next.focus()
  }
}
</script>

<template>
  <div class="review-list">
    <p v-if="loading" role="status">{{ t('review.loading') }}</p>
    <div v-else-if="failed" class="review-list-error">
      <p role="alert">{{ t('review.list.loadError') }}</p>
      <AppButton class="review-list-retry" type="button" @click="emit('retry')">
        {{ t('review.retry') }}
      </AppButton>
    </div>
    <template v-else>
      <p v-if="items.length === 0" class="review-list-empty">{{ t('review.list.empty') }}</p>
      <ul v-else ref="list" class="review-list-items" :aria-label="t('review.list.label')">
        <li v-for="item in items" :key="item.aggregated_result_id" class="row-item">
          <label
            v-if="selectable"
            class="row-check-target"
            :for="`review-tick-${item.aggregated_result_id}`"
          >
            <input
              :id="`review-tick-${item.aggregated_result_id}`"
              type="checkbox"
              class="row-check"
              :checked="ticked.has(item.tei_id)"
              @change="emit('toggle', item.tei_id, ($event.target as HTMLInputElement).checked)"
            />
            <span class="row-check-text">{{
              t('review.bulk.tick', { name: reviewItemName(item) })
            }}</span>
          </label>
          <button
            type="button"
            class="row"
            :aria-current="selected === item.tei_id ? 'true' : undefined"
            @click="emit('select', item.tei_id)"
            @keydown="onKeydown"
          >
            <span class="row-main">
              <span class="row-name">{{ reviewItemName(item) }}</span>
              <span class="row-meta">
                {{ item.tei_id }}
                <span v-if="item.override_source" class="row-flag">{{
                  t('review.list.authority', { source: item.override_source })
                }}</span>
                <span v-if="item.has_authority_conflict" class="row-flag">{{
                  t('review.list.conflict')
                }}</span>
                <span v-if="item.has_prediction_error" class="row-flag">{{
                  t('review.list.error')
                }}</span>
              </span>
            </span>
            <span class="row-badges">
              <VocabBadge
                :value="item.certainty_tier"
                kind="tier"
                :tone="toneOf(item.certainty_tier)"
              />
              <VocabBadge :value="item.final_label" kind="label" />
              <span class="row-state">{{ item.workflow_state }}</span>
            </span>
          </button>
        </li>
      </ul>
      <AppButton
        v-if="hasMore"
        class="review-list-more"
        type="button"
        :disabled="loadingMore"
        @click="emit('loadMore')"
      >
        {{ t('review.loadMore') }}
      </AppButton>
    </template>
  </div>
</template>

<style scoped>
.review-list-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0 0 var(--space-3);
  padding: 0;
  list-style: none;
}

.row-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.row-check-target {
  display: inline-flex;
  flex: none;
  min-inline-size: var(--control-min-size);
  min-block-size: var(--control-min-size);
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.row-check-text {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.row {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--radius-card);
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.row:hover {
  background: var(--surface-1);
}

.row[aria-current='true'] {
  border-color: var(--accent);
  background: var(--surface-1);
}

.row-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.row-name {
  font-weight: var(--weight-semibold);
}

.row-meta {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}

.row-flag {
  margin-left: var(--space-2);
}

.row-badges {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-1);
}

.row-state {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.review-list-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.review-list-error p {
  margin: 0;
  color: var(--critical-text);
}

.review-list-empty {
  color: var(--text-secondary);
}
</style>
