<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'

import type { DatasetSnapshot } from './useSnapshotImport'
import { useSnapshotSourceMembers } from './useSnapshots'

const props = defineProps<{ snapshot: DatasetSnapshot }>()

const { t, d, n } = useI18n()

const snapshotId = computed(() => props.snapshot.id)
const isExpanded = ref(false)
const members = useSnapshotSourceMembers(snapshotId, isExpanded)
const membersId = computed(() => `snapshot-members-${props.snapshot.id}`)

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

function toggleMembers(): void {
  isExpanded.value = !isExpanded.value
}
</script>

<template>
  <li class="snapshot">
    <div class="snapshot-head">
      <span class="snapshot-status" :class="`snapshot-status--${snapshot.status}`">{{
        statusLabel
      }}</span>
      <time :datetime="snapshot.created_at" class="snapshot-created">{{
        d(new Date(snapshot.created_at), 'timestamp')
      }}</time>
    </div>
    <dl class="snapshot-facts">
      <div v-if="snapshot.record_count != null" class="snapshot-fact">
        <dt>{{ t('projects.snapshots.recordCount') }}</dt>
        <dd>{{ n(snapshot.record_count, 'integer') }}</dd>
      </div>
      <div class="snapshot-fact">
        <dt>{{ t('projects.snapshots.parserVersion') }}</dt>
        <dd>{{ snapshot.parser_version }}</dd>
      </div>
      <div class="snapshot-fact">
        <dt>{{ t('projects.snapshots.checksum') }}</dt>
        <dd>
          <code class="snapshot-checksum">{{ snapshot.source_sha256 }}</code>
        </dd>
      </div>
    </dl>
    <RouterLink
      v-if="snapshot.status === 'ready'"
      class="snapshot-runs-link"
      :to="{
        name: 'snapshotRuns',
        params: { projectId: snapshot.project_id, snapshotId: snapshot.id },
      }"
    >
      {{ t('projects.snapshots.openRuns') }}
    </RouterLink>
    <p v-if="snapshot.failure_diagnostic" class="snapshot-failure">
      {{ snapshot.failure_diagnostic }}
    </p>

    <button
      type="button"
      class="snapshot-toggle"
      :aria-expanded="isExpanded"
      :aria-controls="membersId"
      @click="toggleMembers"
    >
      {{ isExpanded ? t('projects.snapshots.hideMembers') : t('projects.snapshots.showMembers') }}
    </button>
    <div v-if="isExpanded" :id="membersId" class="snapshot-members">
      <p v-if="members.isPending.value" role="status">{{ t('projects.loading') }}</p>
      <div v-else-if="members.isError.value" class="snapshot-members-error">
        <p role="alert">{{ t('projects.snapshots.membersLoadError') }}</p>
        <AppButton class="snapshot-members-retry" type="button" @click="() => members.refetch()">
          {{ t('projects.retry') }}
        </AppButton>
      </div>
      <table v-else-if="members.data.value" class="snapshot-members-table">
        <caption class="snapshot-members-caption">
          {{
            t('projects.snapshots.members.label')
          }}
        </caption>
        <thead>
          <tr>
            <th scope="col">{{ t('projects.snapshots.members.name') }}</th>
            <th scope="col">{{ t('projects.snapshots.members.mediaType') }}</th>
            <th scope="col">{{ t('projects.snapshots.members.size') }}</th>
            <th scope="col">{{ t('projects.snapshots.members.checksum') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="member in members.data.value" :key="member.id">
            <td>{{ member.logical_name }}</td>
            <td>{{ member.media_type }}</td>
            <td>
              {{ t('projects.snapshots.members.bytes', { size: n(member.byte_size, 'integer') }) }}
            </td>
            <td>
              <code class="snapshot-checksum">{{ member.sha256 }}</code>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </li>
</template>

<style scoped>
.snapshot-runs-link {
  display: inline-block;
  margin-right: var(--space-4);
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.snapshot {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.snapshot-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.snapshot-status {
  font-weight: var(--weight-semibold);
}

.snapshot-status--ready {
  color: var(--good);
}

.snapshot-status--failed {
  color: var(--critical);
}

.snapshot-created {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

.snapshot-facts {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-body);
}

.snapshot-fact {
  display: flex;
  gap: var(--space-2);
}

.snapshot-fact dt {
  color: var(--text-secondary);
}

.snapshot-fact dd {
  margin: 0;
  min-width: 0;
}

.snapshot-checksum {
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}

.snapshot-failure {
  margin: 0 0 var(--space-3);
  color: var(--critical);
}

.snapshot-toggle {
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  font-size: var(--font-size-small);
  color: var(--accent);
  text-underline-offset: 0.2em;
  text-decoration: underline;
  cursor: pointer;
}

.snapshot-members {
  margin-top: var(--space-3);
}

.snapshot-members-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.snapshot-members-error p {
  margin: 0;
  color: var(--critical);
}

.snapshot-members-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-small);
}

.snapshot-members-caption {
  margin-bottom: var(--space-2);
  text-align: left;
  color: var(--text-secondary);
}

.snapshot-members-table th,
.snapshot-members-table td {
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
</style>
