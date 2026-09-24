<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import AppProgress from '@/components/base/AppProgress.vue'

import type { MethodExecutionSummary } from './useRunDetail'

const props = defineProps<{ execution: MethodExecutionSummary }>()

const { t, n } = useI18n()

const statusLabel = computed(() => {
  switch (props.execution.status) {
    case 'pending':
      return t('runs.status.pending')
    case 'queued':
      return t('runs.status.queued')
    case 'running':
      return t('runs.status.running')
    case 'completed':
      return t('runs.status.completed')
    case 'completed_with_errors':
      return t('runs.status.completedWithErrors')
    case 'failed':
      return t('runs.status.failed')
    case 'cancelled':
      return t('runs.status.cancelled')
  }
  return props.execution.status
})
</script>

<template>
  <li class="execution">
    <div class="execution-head">
      <h3 class="execution-name">{{ execution.method_name }}</h3>
      <span class="execution-status" :class="`execution-status--${execution.status}`">{{
        statusLabel
      }}</span>
    </div>
    <AppProgress
      :percentage="execution.progress.percentage ?? null"
      :label="t('runs.detail.executionProgressLabel', { method: execution.method_name })"
    />
    <p v-if="execution.progress.total != null" class="execution-counts">
      {{
        t('runs.item.progressValue', {
          completed: n(execution.progress.completed, 'integer'),
          total: n(execution.progress.total, 'integer'),
          failed: n(execution.progress.failed, 'integer'),
        })
      }}
    </p>
    <div v-if="execution.failure_class || execution.failure_diagnostic" class="execution-failure">
      <p v-if="execution.failure_class" class="execution-failure-class">
        {{ execution.failure_class }}
      </p>
      <p v-if="execution.failure_diagnostic" class="execution-failure-diagnostic">
        {{ execution.failure_diagnostic }}
      </p>
    </div>
  </li>
</template>

<style scoped>
.execution {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.execution-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}

.execution-name {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.execution-status {
  font-weight: var(--weight-semibold);
}

.execution-status--completed {
  color: var(--good);
}

.execution-status--failed,
.execution-status--completed_with_errors {
  color: var(--critical);
}

.execution-counts {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.execution-failure {
  color: var(--critical);
}

.execution-failure p {
  margin: 0;
}

.execution-failure-class {
  font-weight: var(--weight-semibold);
}
</style>
