<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppSelectField from '@/components/base/AppSelectField.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useDebouncedValue } from '@/composables/useDebouncedValue'

import type { ReviewFilters } from './useReviewFilters'
import {
  AGREEMENT_TIERS,
  CANONICAL_LABELS,
  WORKFLOW_STATES,
  useVocabularyGloss,
} from '@/composables/useVocabulary'
import type { components } from '@/api/schema'

type AgreementTier = components['schemas']['AgreementTier']
type PredictionStatus = components['schemas']['PredictionStatus']
type ReviewWorkflowState = components['schemas']['ReviewWorkflowState']

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

    <AppTextField
      id="review-q"
      v-model="search"
      class="filter"
      :label="t('review.filters.search')"
      type="search"
      autocomplete="off"
    />

    <AppSelectField
      id="review-sort"
      class="filter"
      :label="t('review.filters.sort')"
      :model-value="filters.sort"
      @update:model-value="emit('update', { sort: $event })"
    >
      <option value="uncertainty">{{ t('review.filters.sortUncertainty') }}</option>
      <option value="tei_id">{{ t('review.filters.sortTei') }}</option>
    </AppSelectField>

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

    <AppSelectField
      id="review-label"
      class="filter"
      :label="t('review.filters.label')"
      :model-value="filters.finalLabel"
      @update:model-value="emit('update', { finalLabel: $event })"
    >
      <option :value="null">{{ t('review.filters.any') }}</option>
      <option v-for="label in CANONICAL_LABELS" :key="label" :value="label">{{ label }}</option>
    </AppSelectField>

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

    <AppSelectField
      v-if="!simple"
      id="review-conflict"
      class="filter"
      :label="t('review.filters.authorityConflict')"
      :model-value="filters.hasAuthorityConflict"
      @update:model-value="emit('update', { hasAuthorityConflict: $event })"
    >
      <option :value="null">{{ t('review.filters.any') }}</option>
      <option :value="true">{{ t('review.filters.yes') }}</option>
      <option :value="false">{{ t('review.filters.no') }}</option>
    </AppSelectField>

    <AppSelectField
      v-if="!simple"
      id="review-error"
      class="filter"
      :label="t('review.filters.predictionError')"
      :model-value="filters.hasPredictionError"
      @update:model-value="emit('update', { hasPredictionError: $event })"
    >
      <option :value="null">{{ t('review.filters.any') }}</option>
      <option :value="true">{{ t('review.filters.yes') }}</option>
      <option :value="false">{{ t('review.filters.no') }}</option>
    </AppSelectField>

    <AppSelectField
      v-if="!simple"
      id="review-method"
      class="filter"
      :label="t('review.filters.method')"
      :model-value="filters.methodName"
      @update:model-value="emit('update', { methodName: $event })"
    >
      <option :value="null">{{ t('review.filters.any') }}</option>
      <option v-for="name in methodNames" :key="name" :value="name">{{ name }}</option>
    </AppSelectField>

    <template v-if="!simple && filters.methodName">
      <AppSelectField
        id="review-method-label"
        class="filter"
        :label="t('review.filters.methodLabel')"
        :model-value="filters.methodLabel"
        @update:model-value="emit('update', { methodLabel: $event })"
      >
        <option :value="null">{{ t('review.filters.any') }}</option>
        <option v-for="label in CANONICAL_LABELS" :key="label" :value="label">{{ label }}</option>
      </AppSelectField>
      <AppSelectField
        id="review-method-status"
        class="filter"
        :label="t('review.filters.predictionStatus')"
        :model-value="filters.predictionStatus"
        @update:model-value="emit('update', { predictionStatus: $event })"
      >
        <option :value="null">{{ t('review.filters.any') }}</option>
        <option v-for="status in PREDICTION_STATUSES" :key="status" :value="status">
          {{ status }}
        </option>
      </AppSelectField>
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

.filters {
  --field-control-width: 100%;
}

.filter > label,
.filter > legend {
  padding: 0;
  color: var(--text-secondary);
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
