<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'

import type { MethodExecutionSummary } from './useRunDetail'
import type { AggregationExecution } from './useAggregations'
import { useStatusLabel } from './useStatusLabel'

const props = withDefaults(
  defineProps<{
    aggregation: AggregationExecution
    projectId: string
    executions: readonly MethodExecutionSummary[]
    title: string
    featured?: boolean
  }>(),
  { featured: false },
)

const { t, d, n } = useI18n()
const label = useStatusLabel()

const statusLabel = computed(() => label(props.aggregation.status))
const strategyLabel = computed(() =>
  props.aggregation.strategy === 'reference_v1'
    ? t('aggregations.item.referenceStrategy')
    : props.aggregation.strategy,
)
const selectedMethods = computed(() => {
  const executionsById = new Map(props.executions.map((execution) => [execution.id, execution]))
  return props.aggregation.method_execution_ids.map((id) => {
    const execution = executionsById.get(id)
    return {
      id,
      name: execution?.method_name ?? id,
      status: execution ? label(execution.status) : t('aggregations.item.executionUnavailable'),
    }
  })
})
const excludedMethods = computed(() => {
  const selectedIds = new Set(props.aggregation.method_execution_ids)
  return props.executions.filter((execution) => !selectedIds.has(execution.id))
})
</script>

<template>
  <li class="aggregation" :class="{ 'aggregation--featured': featured }">
    <div class="aggregation-head">
      <h3 class="aggregation-title">{{ title }}</h3>
      <span class="aggregation-status" :class="`aggregation-status--${aggregation.status}`">
        {{ statusLabel }}
      </span>
    </div>

    <p v-if="featured && aggregation.status === 'completed'" class="aggregation-summary">
      {{ t('aggregations.item.ready') }}
    </p>

    <dl class="aggregation-facts">
      <div class="aggregation-fact">
        <dt>{{ t('aggregations.item.strategy') }}</dt>
        <dd>{{ strategyLabel }}</dd>
      </div>
      <div class="aggregation-fact">
        <dt>{{ t('aggregations.detail.created') }}</dt>
        <dd>
          <time :datetime="aggregation.created_at">
            {{ d(new Date(aggregation.created_at), 'timestamp') }}
          </time>
        </dd>
      </div>
      <div v-if="!featured" class="aggregation-fact">
        <dt>{{ t('aggregations.item.selection') }}</dt>
        <dd>
          {{
            t('aggregations.item.selectionValue', {
              count: n(aggregation.method_execution_ids.length, 'integer'),
            })
          }}
        </dd>
      </div>
    </dl>

    <details v-if="featured" class="aggregation-selection">
      <summary>
        {{
          t('aggregations.item.selectedMethods', {
            count: n(selectedMethods.length, 'integer'),
          })
        }}
      </summary>
      <ul>
        <li v-for="method in selectedMethods" :key="method.id">
          <code>{{ method.name }}</code>
          <span>{{ method.status }}</span>
        </li>
      </ul>
    </details>

    <div v-if="featured && excludedMethods.length" class="aggregation-excluded">
      <p>
        {{
          t('aggregations.item.notSelected', {
            count: n(excludedMethods.length, 'integer'),
          })
        }}
      </p>
      <ul>
        <li v-for="execution in excludedMethods" :key="execution.id">
          <code>{{ execution.method_name }}</code>
          <span>{{ label(execution.status) }}</span>
        </li>
      </ul>
    </div>

    <p v-if="aggregation.failure_diagnostic" class="aggregation-failure">
      {{ aggregation.failure_diagnostic }}
    </p>

    <div class="aggregation-actions">
      <AppButton
        v-if="featured && aggregation.status === 'completed'"
        :to="{
          name: 'review',
          params: {
            projectId,
            runId: aggregation.run_id,
            aggregationId: aggregation.id,
          },
        }"
      >
        {{ t('aggregations.item.review') }}
      </AppButton>
      <RouterLink
        class="aggregation-open"
        :aria-label="
          t('aggregations.item.openLabel', {
            date: d(new Date(aggregation.created_at), 'timestamp'),
          })
        "
        :to="{
          name: 'aggregationDetail',
          params: { projectId, runId: aggregation.run_id, aggregationId: aggregation.id },
        }"
      >
        {{ featured ? t('aggregations.item.details') : t('aggregations.item.open') }}
      </RouterLink>
    </div>
  </li>
</template>

<style scoped>
.aggregation {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.aggregation--featured {
  border-color: var(--accent);
  background: var(--surface-1);
}

.aggregation-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2) var(--space-4);
}

.aggregation-title {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.aggregation-status {
  font-weight: var(--weight-semibold);
}

.aggregation-status--completed {
  color: var(--good);
}

.aggregation-status--failed {
  color: var(--critical-text);
}

.aggregation-summary,
.aggregation-excluded > p {
  margin: 0;
  color: var(--text-secondary);
}

.aggregation-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3) var(--space-8);
  margin: 0;
}

.aggregation-fact {
  display: grid;
  gap: var(--space-1);
}

.aggregation-fact dt {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.aggregation-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.aggregation-selection summary {
  display: flex;
  width: fit-content;
  min-block-size: 2rem;
  align-items: center;
  cursor: pointer;
  font-weight: var(--weight-semibold);
}

.aggregation-selection ul,
.aggregation-excluded ul {
  display: grid;
  gap: var(--space-2);
  margin: var(--space-2) 0 0;
  padding: 0;
  list-style: none;
}

.aggregation-selection li,
.aggregation-excluded li {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-2) var(--space-4);
}

.aggregation-selection li span,
.aggregation-excluded li span {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.aggregation-excluded {
  display: grid;
  gap: var(--space-1);
  padding-block-start: var(--space-3);
  border-block-start: 1px solid var(--border);
}

.aggregation-failure {
  margin: 0;
  color: var(--critical-text);
}

.aggregation-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-4);
}

.aggregation-open {
  display: inline-flex;
  min-block-size: 2rem;
  align-items: center;
  color: var(--accent);
  font-weight: var(--weight-semibold);
  text-underline-offset: 0.2em;
}

@media (pointer: coarse) {
  .aggregation-selection summary,
  .aggregation-open {
    min-block-size: 2.75rem;
  }
}
</style>
