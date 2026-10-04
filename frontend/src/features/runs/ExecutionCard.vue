<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

import AppProgress from '@/components/base/AppProgress.vue'

import { TERMINAL_METHOD_EXECUTION_STATUSES } from '@/composables/useRunDetail'
import LifecycleStatus from '@/components/domain/LifecycleStatus.vue'
import JsonData from '@/components/domain/JsonData.vue'
import ProvenanceValue from '@/components/domain/ProvenanceValue.vue'
import type { components } from '@/api/schema'

type MethodExecutionSummary = components['schemas']['MethodExecutionSummary']

const props = withDefaults(
  defineProps<{
    execution: MethodExecutionSummary
    resultsTo?: RouteLocationRaw
    compact?: boolean
  }>(),
  { compact: false },
)

const { t, n } = useI18n()
const hasFinalResults = computed(() =>
  TERMINAL_METHOD_EXECUTION_STATUSES.has(props.execution.status),
)

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
</script>

<template>
  <li class="execution app-resource-card" :class="{ 'execution--compact': compact }">
    <div class="execution-head">
      <h3 class="execution-name">
        <RouterLink v-if="resultsTo && hasFinalResults" :to="resultsTo">
          {{ execution.method_name }}
        </RouterLink>
        <template v-else>{{ execution.method_name }}</template>
      </h3>
      <LifecycleStatus class="execution-status" :status="execution.status" />
    </div>
    <AppProgress
      v-if="!compact"
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
      <summary :aria-label="t('runs.execution.provenanceFor', { method: execution.method_name })">
        {{ t('runs.execution.provenance') }}
      </summary>
      <dl class="execution-provenance-facts app-fact-list">
        <div
          v-for="row in provenanceRows"
          :key="row.key"
          class="execution-provenance-fact app-fact-list__item"
        >
          <dt>{{ row.label }}</dt>
          <dd>
            <ProvenanceValue :value="row.value" />
          </dd>
        </div>
      </dl>
      <JsonData
        class="execution-provenance-config-disclosure"
        :value="execution.resolved_config"
        :summary="t('runs.provenance.resolvedConfig')"
        compact
      />
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
}

.execution--compact {
  gap: var(--space-1);
}

.execution-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}

.execution-name {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.execution-name a {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.execution-status {
  font-weight: var(--weight-semibold);
}

.execution-counts {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.execution-provenance summary {
  display: flex;
  width: fit-content;
  min-block-size: 2rem;
  align-items: center;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.execution-provenance-facts {
  --app-fact-list-label-width: 10rem;

  margin: var(--space-2) 0;
}

.execution-provenance-config-disclosure {
  margin-block-start: var(--space-2);
}

.execution-failure {
  color: var(--critical-text);
}

.execution-failure p {
  margin: 0;
}

.execution-failure-class {
  font-weight: var(--weight-semibold);
}

@media (pointer: coarse) {
  .execution-provenance summary {
    min-block-size: 2.75rem;
  }
}
</style>
