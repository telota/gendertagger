<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { AggregationExecution } from './useAggregations'
import { useStatusLabel } from './useStatusLabel'

const props = defineProps<{ aggregation: AggregationExecution; projectId: string }>()

const { t, d, n } = useI18n()
const label = useStatusLabel()

const statusLabel = computed(() => label(props.aggregation.status))
</script>

<template>
  <li class="aggregation">
    <div class="aggregation-head">
      <span class="aggregation-status" :class="`aggregation-status--${aggregation.status}`">{{
        statusLabel
      }}</span>
      <time :datetime="aggregation.created_at" class="aggregation-created">{{
        d(new Date(aggregation.created_at), 'timestamp')
      }}</time>
    </div>
    <dl class="aggregation-facts">
      <div class="aggregation-fact">
        <dt>{{ t('aggregations.item.strategy') }}</dt>
        <dd>{{ aggregation.strategy ?? '' }}</dd>
      </div>
      <div class="aggregation-fact">
        <dt>{{ t('aggregations.item.selection') }}</dt>
        <dd>
          {{
            t('aggregations.item.selectionValue', {
              count: n(aggregation.method_execution_ids.length, 'integer'),
            })
          }}
        </dd>
      </div>
      <div class="aggregation-fact">
        <dt>{{ t('aggregations.item.configHash') }}</dt>
        <dd>
          <code class="aggregation-hash">{{ aggregation.config_sha256 }}</code>
        </dd>
      </div>
    </dl>
    <p v-if="aggregation.failure_diagnostic" class="aggregation-failure">
      {{ aggregation.failure_diagnostic }}
    </p>
    <RouterLink
      class="aggregation-open"
      :to="{
        name: 'aggregationDetail',
        params: { projectId, runId: aggregation.run_id, aggregationId: aggregation.id },
      }"
    >
      {{ t('aggregations.item.open') }}
    </RouterLink>
  </li>
</template>

<style scoped>
.aggregation {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.aggregation-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.aggregation-status {
  font-weight: var(--weight-semibold);
}

.aggregation-status--completed {
  color: var(--good);
}

.aggregation-status--failed {
  color: var(--critical);
}

.aggregation-created {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.aggregation-facts {
  display: grid;
  gap: var(--space-2);
  margin: 0;
}

.aggregation-fact {
  display: grid;
  grid-template-columns: 9rem 1fr;
  gap: var(--space-3);
}

.aggregation-fact dt {
  color: var(--text-secondary);
}

.aggregation-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.aggregation-hash {
  font-size: var(--font-size-small);
}

.aggregation-failure {
  margin: var(--space-3) 0 0;
  color: var(--critical);
}

.aggregation-open {
  display: inline-block;
  margin-top: var(--space-3);
  color: var(--accent);
  text-underline-offset: 0.2em;
}
</style>
