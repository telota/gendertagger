<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useDebouncedValue } from '@/composables/useDebouncedValue'

import type { ReviewFilters, ReviewSort } from './useReviewFilters'
import {
  AGREEMENT_TIERS,
  CANONICAL_LABELS,
  WORKFLOW_STATES,
  useVocabularyGloss,
  type AgreementTier,
  type CanonicalLabel,
  type PredictionStatus,
  type ReviewWorkflowState,
} from './useVocabulary'

const props = defineProps<{
  filters: ReviewFilters
  methodNames: readonly string[]
  /** The register's filters: search, order, review state and final label. The rest is for triage. */
  simple?: boolean
  layout?: 'column' | 'panel'
}>()
const emit = defineEmits<{ update: [patch: Partial<ReviewFilters>] }>()

const { t } = useI18n()
const gloss = useVocabularyGloss()

// Search is typed freely and sent to the server once typing pauses; the URL never sees keystrokes.
const SEARCH_DELAY_MS = 300
const search = ref(props.filters.q)
const debouncedSearch = useDebouncedValue(search, SEARCH_DELAY_MS)
watch(debouncedSearch, (value) => {
  if (value !== props.filters.q) emit('update', { q: value })
})
// A queue switch (or a shared link) changes the filter from outside; the box follows it.
watch(
  () => props.filters.q,
  (value) => {
    if (value !== search.value) search.value = value
  },
)

function toggle<T extends string>(current: readonly T[], value: T, on: boolean): T[] {
  return on ? [...current, value] : current.filter((item) => item !== value)
}

function toTriState(value: string): boolean | null {
  return value === 'yes' ? true : value === 'no' ? false : null
}
const fromTriState = (value: boolean | null): string =>
  value === null ? 'any' : value ? 'yes' : 'no'

const PREDICTION_STATUSES: readonly PredictionStatus[] = ['success', 'abstain', 'error']
</script>

<template>
  <form
    class="filters"
    :class="{ 'filters--panel': layout === 'panel' }"
    role="search"
    novalidate
    @submit.prevent
  >
    <h2 class="filters-title">{{ t('review.filters.title') }}</h2>

    <div class="filter">
      <label for="review-q">{{ t('review.filters.search') }}</label>
      <input id="review-q" v-model="search" type="search" autocomplete="off" />
    </div>

    <div class="filter">
      <label for="review-sort">{{ t('review.filters.sort') }}</label>
      <select
        id="review-sort"
        :value="filters.sort"
        @change="emit('update', { sort: ($event.target as HTMLSelectElement).value as ReviewSort })"
      >
        <option value="uncertainty">{{ t('review.filters.sortUncertainty') }}</option>
        <option value="tei_id">{{ t('review.filters.sortTei') }}</option>
      </select>
    </div>

    <fieldset class="filter">
      <legend>{{ t('review.filters.states') }}</legend>
      <div v-for="state in WORKFLOW_STATES" :key="state" class="check">
        <input
          :id="`review-state-${state}`"
          type="checkbox"
          :checked="filters.workflowStates.includes(state)"
          @change="
            emit('update', {
              workflowStates: toggle<ReviewWorkflowState>(
                filters.workflowStates,
                state,
                ($event.target as HTMLInputElement).checked,
              ),
            })
          "
        />
        <label :for="`review-state-${state}`">
          <span class="token">{{ state }}</span
          >{{ ' ' }}<span class="gloss">{{ gloss.workflow(state) }}</span>
        </label>
      </div>
    </fieldset>

    <div class="filter">
      <label for="review-label">{{ t('review.filters.label') }}</label>
      <select
        id="review-label"
        :value="filters.finalLabel ?? ''"
        @change="
          emit('update', {
            finalLabel: (($event.target as HTMLSelectElement).value ||
              null) as CanonicalLabel | null,
          })
        "
      >
        <option value="">{{ t('review.filters.any') }}</option>
        <option v-for="label in CANONICAL_LABELS" :key="label" :value="label">{{ label }}</option>
      </select>
    </div>

    <fieldset v-if="!simple" class="filter">
      <legend>{{ t('review.filters.agreement') }}</legend>
      <div v-for="tier in AGREEMENT_TIERS" :key="tier" class="check">
        <input
          :id="`review-agreement-${tier}`"
          type="checkbox"
          :checked="filters.agreementTiers.includes(tier)"
          @change="
            emit('update', {
              agreementTiers: toggle<AgreementTier>(
                filters.agreementTiers,
                tier,
                ($event.target as HTMLInputElement).checked,
              ),
            })
          "
        />
        <label :for="`review-agreement-${tier}`">
          <span class="token">{{ tier }}</span
          >{{ ' ' }}<span class="gloss">{{ gloss.agreement(tier) }}</span>
        </label>
      </div>
    </fieldset>

    <div v-if="!simple" class="filter">
      <label for="review-conflict">{{ t('review.filters.authorityConflict') }}</label>
      <select
        id="review-conflict"
        :value="fromTriState(filters.hasAuthorityConflict)"
        @change="
          emit('update', {
            hasAuthorityConflict: toTriState(($event.target as HTMLSelectElement).value),
          })
        "
      >
        <option value="any">{{ t('review.filters.any') }}</option>
        <option value="yes">{{ t('review.filters.yes') }}</option>
        <option value="no">{{ t('review.filters.no') }}</option>
      </select>
    </div>

    <div v-if="!simple" class="filter">
      <label for="review-error">{{ t('review.filters.predictionError') }}</label>
      <select
        id="review-error"
        :value="fromTriState(filters.hasPredictionError)"
        @change="
          emit('update', {
            hasPredictionError: toTriState(($event.target as HTMLSelectElement).value),
          })
        "
      >
        <option value="any">{{ t('review.filters.any') }}</option>
        <option value="yes">{{ t('review.filters.yes') }}</option>
        <option value="no">{{ t('review.filters.no') }}</option>
      </select>
    </div>

    <div v-if="!simple" class="filter">
      <label for="review-method">{{ t('review.filters.method') }}</label>
      <select
        id="review-method"
        :value="filters.methodName ?? ''"
        @change="
          emit('update', {
            methodName: ($event.target as HTMLSelectElement).value || null,
          })
        "
      >
        <option value="">{{ t('review.filters.any') }}</option>
        <option v-for="name in methodNames" :key="name" :value="name">{{ name }}</option>
      </select>
    </div>

    <template v-if="!simple && filters.methodName">
      <div class="filter">
        <label for="review-method-label">{{ t('review.filters.methodLabel') }}</label>
        <select
          id="review-method-label"
          :value="filters.methodLabel ?? ''"
          @change="
            emit('update', {
              methodLabel: (($event.target as HTMLSelectElement).value ||
                null) as CanonicalLabel | null,
            })
          "
        >
          <option value="">{{ t('review.filters.any') }}</option>
          <option v-for="label in CANONICAL_LABELS" :key="label" :value="label">{{ label }}</option>
        </select>
      </div>
      <div class="filter">
        <label for="review-method-status">{{ t('review.filters.predictionStatus') }}</label>
        <select
          id="review-method-status"
          :value="filters.predictionStatus ?? ''"
          @change="
            emit('update', {
              predictionStatus: (($event.target as HTMLSelectElement).value ||
                null) as PredictionStatus | null,
            })
          "
        >
          <option value="">{{ t('review.filters.any') }}</option>
          <option v-for="status in PREDICTION_STATUSES" :key="status" :value="status">
            {{ status }}
          </option>
        </select>
      </div>
    </template>

    <p class="filters-hint">{{ t('review.filters.hint') }}</p>
  </form>
</template>

<style scoped>
.filters {
  min-width: 0;
  overflow-wrap: anywhere;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.filters--panel {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr));
  align-items: start;
  gap: var(--space-4);
}

.filters--panel .filters-title,
.filters--panel .filters-hint {
  grid-column: 1 / -1;
}

.filters-title {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.filter {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  border: 0;
  font-size: var(--font-size-small);
}

.filter > label,
.filter > legend {
  padding: 0;
  color: var(--text-secondary);
}

.filter select,
.filter input[type='search'] {
  width: 100%;
  font: inherit;
}

.check {
  display: flex;
  min-block-size: var(--control-min-size);
  align-items: center;
  gap: var(--space-2);
}

.check input {
  flex: none;
}

.check label {
  display: inline-flex;
  min-width: 0;
  min-block-size: var(--control-min-size);
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  column-gap: var(--space-1);
  overflow-wrap: anywhere;
  cursor: pointer;
}

.token {
  font-family: var(--font-mono, ui-monospace, monospace);
}

.gloss {
  color: var(--text-secondary);
}

.filters-hint {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
</style>
