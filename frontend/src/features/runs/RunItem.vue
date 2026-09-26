<script setup lang="ts">
import { computed } from 'vue'
import { PhArrowRight } from '@phosphor-icons/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import AppButton from '@/components/base/AppButton.vue'

import type { Run } from './useRuns'
import { useStatusLabel } from './useStatusLabel'

const props = defineProps<{ run: Run; projectId: string }>()

const { t, d, n } = useI18n()
const label = useStatusLabel()

const statusLabel = computed(() => label(props.run.status))
const date = computed(() => d(new Date(props.run.created_at), 'timestamp'))
const destination = computed(() => ({
  name: 'runDetail',
  params: {
    projectId: props.projectId,
    snapshotId: props.run.dataset_snapshot_id,
    runId: props.run.id,
  },
}))

const methodNames = computed(() => props.run.resolved_config.methods.map((m) => m.name).join(', '))
</script>

<template>
  <li class="run">
    <div class="run-content">
      <div class="run-head">
        <h3 class="run-title">
          <RouterLink :to="destination">{{ t('runs.item.title', { date }) }}</RouterLink>
        </h3>
        <span class="run-status" :class="`run-status--${run.status}`">{{ statusLabel }}</span>
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
      </dl>
      <p v-if="run.failure_diagnostic" class="run-failure">{{ run.failure_diagnostic }}</p>
    </div>
    <AppButton
      class="run-open"
      variant="ghost"
      :to="destination"
      :aria-label="t('runs.item.openNamed', { date })"
    >
      {{ t('runs.item.open') }}
      <PhArrowRight :size="18" aria-hidden="true" />
    </AppButton>
  </li>
</template>

<style scoped>
.run {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4) var(--space-6);
  min-inline-size: 0;
  padding: var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}
.run-content {
  flex: 1 1 24rem;
  min-inline-size: 0;
}
.run-title {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}
.run-title a {
  color: inherit;
  text-decoration: none;
}
.run-title a:hover {
  text-decoration: underline;
  text-underline-offset: 0.2em;
}

.run-head {
  display: flex;
  flex-wrap: wrap;
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
  color: var(--critical-text);
}

.run-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-6);
  margin: 0;
}

.run-fact {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.run-fact dt {
  color: var(--text-secondary);
}

.run-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.run-open {
  flex-shrink: 0;
}

.run-failure {
  margin: var(--space-3) 0 0;
  color: var(--critical-text);
}
</style>
