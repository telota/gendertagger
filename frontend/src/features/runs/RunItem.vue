<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { Run } from './useRuns'
import { useStatusLabel } from './useStatusLabel'

const props = defineProps<{ run: Run; projectId: string }>()

const { t, d, n } = useI18n()
const label = useStatusLabel()

const statusLabel = computed(() => label(props.run.status))

const methodNames = computed(() => props.run.resolved_config.methods.map((m) => m.name).join(', '))
</script>

<template>
  <li class="run">
    <div class="run-head">
      <span class="run-status" :class="`run-status--${run.status}`">{{ statusLabel }}</span>
      <time :datetime="run.created_at" class="run-created">{{
        d(new Date(run.created_at), 'timestamp')
      }}</time>
    </div>
    <dl class="run-facts">
      <div class="run-fact">
        <dt>{{ t('runs.item.methods') }}</dt>
        <dd>{{ methodNames }}</dd>
      </div>
      <div v-if="run.progress.total != null" class="run-fact">
        <dt>{{ t('runs.item.progress') }}</dt>
        <dd>
          {{
            t('runs.item.progressValue', {
              completed: n(run.progress.completed, 'integer'),
              total: n(run.progress.total, 'integer'),
              failed: n(run.progress.failed, 'integer'),
            })
          }}
        </dd>
      </div>
      <div class="run-fact">
        <dt>{{ t('runs.item.configHash') }}</dt>
        <dd>
          <code class="run-hash">{{ run.config_sha256 }}</code>
        </dd>
      </div>
    </dl>
    <p v-if="run.failure_diagnostic" class="run-failure">{{ run.failure_diagnostic }}</p>
    <RouterLink
      class="run-open"
      :to="{
        name: 'runDetail',
        params: { projectId, snapshotId: run.dataset_snapshot_id, runId: run.id },
      }"
    >
      {{ t('runs.item.open') }}
    </RouterLink>
  </li>
</template>

<style scoped>
.run {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.run-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.run-status {
  font-weight: var(--weight-semibold);
}

.run-status--completed {
  color: var(--good);
}

.run-status--failed,
.run-status--completed_with_errors {
  color: var(--critical);
}

.run-created {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.run-facts {
  display: grid;
  gap: var(--space-2);
  margin: 0;
}

.run-fact {
  display: grid;
  grid-template-columns: 9rem 1fr;
  gap: var(--space-3);
}

.run-fact dt {
  color: var(--text-secondary);
}

.run-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.run-hash {
  font-size: var(--font-size-small);
}

.run-open {
  display: inline-block;
  margin-top: var(--space-3);
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.run-failure {
  margin: var(--space-3) 0 0;
  color: var(--critical);
}
</style>
