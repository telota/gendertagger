<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useStatusLabel } from '@/features/runs/useStatusLabel'

import type { EvaluationExecution } from './useEvaluations'

const props = defineProps<{ evaluation: EvaluationExecution; projectId: string }>()

const { t, d, n } = useI18n()
const label = useStatusLabel()
const statusLabel = computed(() => label(props.evaluation.status))
</script>

<template>
  <li class="evaluation">
    <div class="evaluation-head">
      <span class="evaluation-status" :class="`evaluation-status--${evaluation.status}`">{{
        statusLabel
      }}</span>
      <time :datetime="evaluation.created_at" class="evaluation-created">{{
        d(new Date(evaluation.created_at), 'timestamp')
      }}</time>
    </div>
    <dl class="evaluation-facts">
      <div class="evaluation-fact">
        <dt>{{ t('evaluation.item.definition') }}</dt>
        <dd>{{ evaluation.definition ?? '' }}</dd>
      </div>
      <div class="evaluation-fact">
        <dt>{{ t('evaluation.item.methods') }}</dt>
        <dd>
          {{
            t('evaluation.item.methodsValue', {
              count: n(evaluation.method_execution_ids.length, 'integer'),
            })
          }}
        </dd>
      </div>
      <div class="evaluation-fact">
        <dt>{{ t('evaluation.item.configHash') }}</dt>
        <dd>
          <code class="evaluation-hash">{{ evaluation.config_sha256 }}</code>
        </dd>
      </div>
    </dl>
    <p v-if="evaluation.failure_diagnostic" class="evaluation-failure">
      {{ evaluation.failure_diagnostic }}
    </p>
    <RouterLink
      class="evaluation-open"
      :to="{
        name: 'evaluationDetail',
        params: { projectId, runId: evaluation.run_id, evaluationId: evaluation.id },
      }"
    >
      {{ t('evaluation.item.open') }}
    </RouterLink>
  </li>
</template>

<style scoped>
.evaluation {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.evaluation-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.evaluation-status {
  font-weight: var(--weight-semibold);
}

.evaluation-status--completed {
  color: var(--good);
}

.evaluation-status--failed {
  color: var(--critical-text);
}

.evaluation-created {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.evaluation-facts {
  display: grid;
  gap: var(--space-2);
  margin: 0;
}

.evaluation-fact {
  display: grid;
  grid-template-columns: 9rem 1fr;
  gap: var(--space-3);
}

.evaluation-fact dt {
  color: var(--text-secondary);
}

.evaluation-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.evaluation-hash {
  font-size: var(--font-size-small);
}

.evaluation-failure {
  margin: var(--space-3) 0 0;
  color: var(--critical-text);
}

.evaluation-open {
  display: inline-block;
  margin-top: var(--space-3);
  color: var(--accent);
  text-underline-offset: 0.2em;
}
</style>
