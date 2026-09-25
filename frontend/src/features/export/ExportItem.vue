<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useStatusLabel } from '@/features/runs/useStatusLabel'

import type { ExportExecution } from './useExports'

const props = defineProps<{ item: ExportExecution; projectId: string }>()

const { t, d } = useI18n()
const label = useStatusLabel()
const statusLabel = computed(() => label(props.item.status))
</script>

<template>
  <li class="export">
    <div class="export-head">
      <span class="export-status" :class="`export-status--${item.status}`">{{ statusLabel }}</span>
      <time :datetime="item.created_at" class="export-created">{{
        d(new Date(item.created_at), 'timestamp')
      }}</time>
    </div>
    <dl class="export-facts">
      <div class="export-fact">
        <dt>{{ t('export.item.format') }}</dt>
        <dd class="export-token">{{ item.format }}</dd>
      </div>
      <div class="export-fact">
        <dt>{{ t('export.item.policy') }}</dt>
        <dd class="export-token">{{ item.label_source_policy ?? 'machine_aggregation' }}</dd>
      </div>
      <div v-if="item.tei_profile" class="export-fact">
        <dt>{{ t('export.item.profile') }}</dt>
        <dd class="export-token">{{ item.tei_profile }}</dd>
      </div>
    </dl>
    <p v-if="item.failure_diagnostic" class="export-failure">{{ item.failure_diagnostic }}</p>
    <RouterLink
      class="export-open"
      :to="{
        name: 'exportDetail',
        params: { projectId, runId: item.run_id, exportId: item.id },
      }"
    >
      {{ t('export.item.open') }}
    </RouterLink>
  </li>
</template>

<style scoped>
.export {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.export-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.export-status {
  font-weight: var(--weight-semibold);
}

.export-status--completed {
  color: var(--good);
}

.export-status--failed {
  color: var(--critical-text);
}

.export-created {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.export-facts {
  display: grid;
  gap: var(--space-2);
  margin: 0;
}

.export-fact {
  display: grid;
  grid-template-columns: 11rem 1fr;
  gap: var(--space-3);
}

.export-fact dt {
  color: var(--text-secondary);
}

.export-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.export-token {
  font-family: var(--font-mono, ui-monospace, monospace);
}

.export-failure {
  margin: var(--space-3) 0 0;
  color: var(--critical-text);
}

.export-open {
  display: inline-block;
  margin-top: var(--space-3);
  color: var(--accent);
  text-underline-offset: 0.2em;
}
</style>
