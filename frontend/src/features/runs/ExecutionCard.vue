<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import AppProgress from '@/components/base/AppProgress.vue'

import type { MethodExecutionSummary } from './useRunDetail'
import { useStatusLabel } from './useStatusLabel'

const props = defineProps<{ execution: MethodExecutionSummary }>()

const { t, n } = useI18n()
const label = useStatusLabel()

const statusLabel = computed(() => label(props.execution.status))

// The method's own identity: which implementation, which model and prompt produced these results
// (docs/11). Optional entries appear only for methods that have them; the ones every execution
// carries always do.
interface ProvenanceRow {
  key: string
  label: string
  value: string
}
const provenanceRows = computed<ProvenanceRow[]>(() => {
  const e = props.execution
  const always: ProvenanceRow[] = [
    {
      key: 'implementationVersion',
      label: t('runs.execution.implementationVersion'),
      value: e.implementation_version,
    },
    {
      key: 'normalizationVersion',
      label: t('runs.execution.normalizationVersion'),
      value: e.normalization_version,
    },
    { key: 'configHash', label: t('runs.item.configHash'), value: e.config_sha256 },
  ]
  const optional: [string, string, string | null | undefined][] = [
    ['modelIdentifier', t('runs.execution.modelIdentifier'), e.model_identifier],
    ['modelRevision', t('runs.execution.modelRevision'), e.model_revision],
    ['modelChecksum', t('runs.execution.modelChecksum'), e.model_checksum],
    ['promptVersion', t('runs.execution.promptVersion'), e.prompt_version],
    ['schemaVersion', t('runs.execution.schemaVersion'), e.schema_version],
  ]
  for (const [key, label, value] of optional) {
    if (value) always.push({ key, label, value })
  }
  return always
})
const resolvedConfig = computed(() => JSON.stringify(props.execution.resolved_config, null, 2))
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
    <details class="execution-provenance">
      <summary>{{ t('runs.execution.provenance') }}</summary>
      <dl class="execution-provenance-facts">
        <div v-for="row in provenanceRows" :key="row.key" class="execution-provenance-fact">
          <dt>{{ row.label }}</dt>
          <dd>
            <code class="execution-provenance-value">{{ row.value }}</code>
          </dd>
        </div>
      </dl>
      <pre class="execution-provenance-config">{{ resolvedConfig }}</pre>
    </details>
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

.execution-provenance summary {
  cursor: pointer;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.execution-provenance-facts {
  display: grid;
  gap: var(--space-2);
  margin: var(--space-2) 0;
}

.execution-provenance-fact {
  display: grid;
  grid-template-columns: 10rem 1fr;
  gap: var(--space-3);
}

.execution-provenance-fact dt {
  color: var(--text-secondary);
}

.execution-provenance-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.execution-provenance-value {
  font-size: var(--font-size-small);
}

.execution-provenance-config {
  margin: 0;
  padding: var(--space-3);
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
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
