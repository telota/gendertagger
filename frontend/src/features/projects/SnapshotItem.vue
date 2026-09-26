<script setup lang="ts">
import { PhArrowRight } from '@phosphor-icons/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'

import type { DatasetSnapshot } from './useSnapshotImport'

const props = defineProps<{ snapshot: DatasetSnapshot }>()
const { t, d, n } = useI18n()
const date = computed(() => d(new Date(props.snapshot.created_at), 'timestamp'))
const destination = computed(() => ({
  name: 'snapshotDetail',
  params: { projectId: props.snapshot.project_id, snapshotId: props.snapshot.id },
}))
const sourceFormat = computed(() => {
  const format = props.snapshot.import_config?.source_format
  return typeof format === 'string' && ['tei', 'csv', 'xlsx', 'json'].includes(format)
    ? format.toUpperCase()
    : null
})
const statusLabel = computed(() => {
  switch (props.snapshot.status) {
    case 'pending':
      return t('projects.snapshots.status.pending')
    case 'importing':
      return t('projects.snapshots.status.importing')
    case 'ready':
      return t('projects.snapshots.status.ready')
    case 'failed':
      return t('projects.snapshots.status.failed')
  }
  return props.snapshot.status
})
</script>

<template>
  <li class="snapshot">
    <div class="snapshot-content">
      <h2 class="snapshot-title">
        <RouterLink :to="destination" class="snapshot-title-link">
          {{ t('data.snapshotTitle', { date }) }}
        </RouterLink>
      </h2>
      <p class="snapshot-status" :class="`snapshot-status--${snapshot.status}`">
        {{ statusLabel }}
      </p>
      <dl class="snapshot-facts">
        <div v-if="snapshot.record_count != null" class="snapshot-fact">
          <dt>{{ t('projects.snapshots.recordCount') }}</dt>
          <dd>{{ n(snapshot.record_count, 'integer') }}</dd>
        </div>
        <div v-if="sourceFormat" class="snapshot-fact">
          <dt>{{ t('data.sourceFormat') }}</dt>
          <dd>{{ sourceFormat }}</dd>
        </div>
      </dl>
      <p v-if="snapshot.failure_diagnostic" class="snapshot-failure">
        {{ snapshot.failure_diagnostic }}
      </p>
    </div>
    <AppButton
      class="snapshot-open"
      :to="destination"
      variant="ghost"
      :aria-label="t('data.openSnapshotNamed', { date })"
    >
      {{ t('data.openSnapshot') }}
      <PhArrowRight :size="18" aria-hidden="true" />
    </AppButton>
  </li>
</template>

<style scoped>
.snapshot {
  display: grid;
  gap: var(--space-4) var(--space-6);
  min-inline-size: 0;
  padding: var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
  overflow-wrap: anywhere;
}
.snapshot-content {
  min-inline-size: 0;
}
.snapshot-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-title);
}
.snapshot-title-link {
  color: inherit;
  text-decoration: none;
}
.snapshot-title-link:hover {
  text-decoration: underline;
  text-underline-offset: 0.2em;
}
.snapshot-status {
  margin: 0 0 var(--space-3);
  font-weight: var(--weight-semibold);
}
.snapshot-status--ready {
  color: var(--good);
}
.snapshot-status--failed,
.snapshot-failure {
  color: var(--critical-text);
}
.snapshot-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-6);
  margin: 0;
  font-size: var(--font-size-small);
}
.snapshot-fact {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-2);
  min-inline-size: 0;
}
.snapshot-fact dt {
  color: var(--text-secondary);
}
.snapshot-fact dd {
  min-inline-size: 0;
  margin: 0;
}
.snapshot-failure {
  max-inline-size: 65ch;
  margin: var(--space-3) 0 0;
}
.snapshot-open {
  align-self: start;
  justify-self: start;
}
.snapshot-open svg {
  flex-shrink: 0;
}
@container snapshot-index (min-width: 40rem) {
  .snapshot {
    grid-template-columns: minmax(0, 1fr) minmax(0, 13rem);
    align-items: start;
  }
  .snapshot-open {
    justify-self: stretch;
  }
}
</style>
