<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import { useSessionStore } from '@/stores/session'

import { useAggregation } from '@/composables/useAggregations'
import { useProject } from '@/composables/useProjects'
import { useRun } from '@/composables/useRunDetail'
import ProjectOverviewSection from './ProjectOverviewSection.vue'
import ProjectReviewStats from './ProjectReviewStats.vue'
import SnapshotRecords from './SnapshotRecords.vue'
import SnapshotStatisticsPanel from './SnapshotStatisticsPanel.vue'
import { useImportedSnapshot } from '@/composables/useSnapshotData'
import { useSnapshotSourceMembers } from './useSnapshots'

const { t, d, n } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const projectId = computed(() => String(route.params.projectId ?? ''))
const snapshotId = computed(() => String(route.params.snapshotId ?? ''))
const enabled = computed(() => session.canUsePrivateNavigation)
const query = useImportedSnapshot(projectId, snapshotId, enabled)
const snapshot = computed(() => {
  const value = query.data.value
  return value?.id === snapshotId.value && value.project_id === projectId.value ? value : null
})
const ready = computed(() => snapshot.value?.status === 'ready')
const terminal = computed(() => ready.value || snapshot.value?.status === 'failed')

// "Stand der Prüfung" belongs to the dataset behind the project's working aggregation (ADR-0035,
// one pointer per project, not per dataset) — D28 moved it here from Übersicht for exactly that
// reason, so it never shows review figures for the wrong dataset. Resolving "is this that dataset"
// needs the project (for the pointer), the aggregation it names (for its run), and that run (for the
// dataset snapshot it ran against) — three chained reads, enabled only once ready and only as far as
// each prior one resolves.
const project = useProject(projectId, computed(() => enabled.value && ready.value))
const workingAggregationId = computed(
  () => project.data.value?.working_aggregation_execution_id ?? null,
)
const workingAggregation = useAggregation(
  computed(() => workingAggregationId.value ?? ''),
  computed(() => workingAggregationId.value !== null),
)
const workingRunId = computed(() => workingAggregation.data.value?.run_id ?? null)
const workingRun = useRun(
  computed(() => workingRunId.value ?? ''),
  computed(() => workingRunId.value !== null),
)
const reviewStatsState = computed<'none' | 'loading' | 'error' | 'current' | 'other'>(() => {
  if (workingAggregationId.value === null) return 'none'
  if (workingAggregation.isPending.value) return 'loading'
  if (workingAggregation.isError.value) return 'error'
  if (workingRunId.value === null) return 'error'
  if (workingRun.isPending.value) return 'loading'
  if (workingRun.isError.value) return 'error'
  return workingRun.data.value?.dataset_snapshot_id === snapshotId.value ? 'current' : 'other'
})
function retryReviewStats(): void {
  if (workingAggregation.isError.value) void workingAggregation.refetch()
  if (workingRun.isError.value) void workingRun.refetch()
}
const membersQuery = useSnapshotSourceMembers(snapshotId, terminal)
const members = computed(
  () =>
    membersQuery.data.value?.filter((member) => member.dataset_snapshot_id === snapshotId.value) ??
    [],
)
const sourceFormat = computed(() => {
  const format = snapshot.value?.import_config?.source_format
  return typeof format === 'string' && ['tei', 'csv', 'xlsx', 'json'].includes(format)
    ? format.toUpperCase()
    : null
})
const statusLabel = computed(() => {
  switch (snapshot.value?.status) {
    case 'pending':
      return t('projects.snapshots.status.pending')
    case 'importing':
      return t('projects.snapshots.status.importing')
    case 'ready':
      return t('projects.snapshots.status.ready')
    case 'failed':
      return t('projects.snapshots.status.failed')
    default:
      return ''
  }
})
watch(
  [() => session.status, () => session.mustChangePassword],
  ([status, mustChangePassword]) => {
    if (status !== 'ready') return
    if (!session.isSignedIn) {
      void router.replace({ name: 'login', query: { redirect: route.fullPath } })
    } else if (mustChangePassword) {
      void router.replace({ name: 'changePassword', query: { redirect: route.fullPath } })
    }
  },
  { immediate: true },
)
</script>

<template>
  <main class="snapshot-detail app-page-frame">
    <header class="snapshot-detail-heading app-page-heading">
      <h1 class="app-page-heading__title">
        {{
          snapshot
            ? t('data.snapshotTitle', { date: d(new Date(snapshot.created_at), 'timestamp') })
            : t('data.detailTitle')
        }}
      </h1>
      <div v-if="ready" class="app-page-heading__actions">
        <AppButton
          variant="ghost"
          :to="{ name: 'snapshotRuns', params: { projectId, snapshotId } }"
          >{{ t('projects.snapshots.openRuns') }}</AppButton
        >
      </div>
    </header>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      announcement="polite"
      >{{ t('data.loading') }}</AppFeedback
    >
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('projects.sessionLoadError') }}
      <template #actions
        ><AppButton variant="ghost" @click="session.initialize()">{{
          t('projects.retry')
        }}</AppButton></template
      >
    </AppFeedback>
    <template v-else-if="enabled">
      <AppFeedback v-if="query.isPending.value" class="app-card" announcement="polite">{{
        t('data.loading')
      }}</AppFeedback>
      <AppFeedback v-else-if="!snapshot" class="app-card" announcement="assertive" tone="critical">
        {{ t('data.snapshotUnavailable') }}
        <template #actions
          ><AppButton
            class="snapshot-detail-retry"
            variant="ghost"
            :disabled="query.isFetching.value"
            @click="query.refetch()"
            >{{ t('projects.retry') }}</AppButton
          ></template
        >
      </AppFeedback>
      <template v-else>
        <dl class="snapshot-summary app-fact-list app-card">
          <div
            class="snapshot-summary-status app-fact-list__item"
            :class="`snapshot-summary-status--${snapshot.status}`"
          >
            <dt>{{ t('data.status') }}</dt>
            <dd>{{ statusLabel }}</dd>
          </div>
          <div v-if="sourceFormat" class="app-fact-list__item">
            <dt>{{ t('data.sourceFormat') }}</dt>
            <dd>{{ sourceFormat }}</dd>
          </div>
        </dl>
        <AppFeedback
          v-if="query.isError.value"
          class="snapshot-detail-feedback app-card"
          announcement="assertive"
          tone="critical"
        >
          {{ t('data.refreshError') }}
          <template #actions
            ><AppButton
              variant="ghost"
              :disabled="query.isFetching.value"
              @click="query.refetch()"
              >{{ t('projects.retry') }}</AppButton
            ></template
          >
        </AppFeedback>
        <AppFeedback
          v-if="!terminal"
          class="snapshot-detail-feedback app-card"
          announcement="polite"
        >
          {{ t('data.importing') }}
        </AppFeedback>
        <AppFeedback
          v-if="snapshot.status === 'failed'"
          class="snapshot-detail-feedback app-card"
          announcement="assertive"
          tone="critical"
        >
          <p>{{ t('data.failed') }}</p>
          <p v-if="snapshot.failure_diagnostic">{{ snapshot.failure_diagnostic }}</p>
        </AppFeedback>
        <SnapshotStatisticsPanel
          v-if="ready"
          :key="`statistics:${session.user?.id}:${snapshot.id}`"
          :project-id="projectId"
          :snapshot-id="snapshot.id"
        />
        <ProjectReviewStats
          v-if="ready && reviewStatsState === 'current'"
          class="snapshot-review-stats app-card app-card--sectioned"
          :project-id="projectId"
          :aggregation-id="workingAggregationId"
        />
        <div
          v-else-if="ready && reviewStatsState === 'loading'"
          class="snapshot-review-stats app-card app-card--sectioned"
        >
          <ProjectOverviewSection :title="t('projects.overview.review.title')">
            <p role="status">{{ t('projects.loading') }}</p>
          </ProjectOverviewSection>
        </div>
        <div
          v-else-if="ready && reviewStatsState === 'error'"
          class="snapshot-review-stats app-card app-card--sectioned"
        >
          <ProjectOverviewSection :title="t('projects.overview.review.title')">
            <AppFeedback tone="critical" announcement="polite">
              {{ t('projects.overview.review.aggregationLoadError') }}
              <template #actions>
                <AppButton type="button" variant="ghost" @click="retryReviewStats">{{
                  t('projects.retry')
                }}</AppButton>
              </template>
            </AppFeedback>
          </ProjectOverviewSection>
        </div>
        <div
          v-else-if="ready && reviewStatsState === 'other'"
          class="snapshot-review-stats app-card app-card--sectioned"
        >
          <ProjectOverviewSection :title="t('projects.overview.review.title')">
            <p class="snapshot-review-stats-note">
              {{ t('projects.overview.review.notCurrentDataset') }}
            </p>
            <AppButton
              :to="{
                name: 'snapshotDetail',
                params: { projectId, snapshotId: workingRun.data.value?.dataset_snapshot_id ?? '' },
              }"
              variant="ghost"
            >
              {{ t('projects.overview.review.goToCurrentDataset') }}
            </AppButton>
          </ProjectOverviewSection>
        </div>
        <div class="snapshot-secondary">
          <details
            v-if="terminal"
            class="snapshot-disclosure snapshot-sources app-card app-card--sectioned"
          >
            <summary>
              <span>{{ t('data.sourceFiles') }}</span>
              <span v-if="membersQuery.isSuccess.value" class="snapshot-disclosure-count">
                {{ n(members.length, 'integer') }}
              </span>
            </summary>
            <div class="snapshot-disclosure-content">
              <AppFeedback v-if="membersQuery.isPending.value" announcement="polite">{{
                t('data.sourcesLoading')
              }}</AppFeedback>
              <AppFeedback
                v-else-if="membersQuery.isError.value"
                announcement="assertive"
                tone="critical"
              >
                {{ t('projects.snapshots.membersLoadError') }}
                <template #actions
                  ><AppButton
                    variant="ghost"
                    :disabled="membersQuery.isFetching.value"
                    @click="membersQuery.refetch()"
                    >{{ t('projects.retry') }}</AppButton
                  ></template
                >
              </AppFeedback>
              <AppScrollRegion v-if="members.length" :label="t('projects.snapshots.members.label')">
                <table class="snapshot-source-table">
                  <thead>
                    <tr>
                      <th scope="col">{{ t('projects.snapshots.members.name') }}</th>
                      <th scope="col">{{ t('projects.snapshots.members.mediaType') }}</th>
                      <th scope="col">{{ t('projects.snapshots.members.size') }}</th>
                      <th scope="col">{{ t('projects.snapshots.members.checksum') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="member in members" :key="member.id">
                      <th scope="row">{{ member.logical_name }}</th>
                      <td>{{ member.media_type }}</td>
                      <td>
                        {{
                          t('projects.snapshots.members.bytes', {
                            size: n(member.byte_size, 'integer'),
                          })
                        }}
                      </td>
                      <td class="snapshot-hash">{{ member.sha256 }}</td>
                    </tr>
                  </tbody>
                </table>
              </AppScrollRegion>
              <p v-else-if="membersQuery.isSuccess.value" class="snapshot-disclosure-empty">
                {{ t('data.sourcesEmpty') }}
              </p>
            </div>
          </details>
          <details class="snapshot-disclosure snapshot-provenance app-card app-card--sectioned">
            <summary>{{ t('data.importDetails') }}</summary>
            <div class="snapshot-disclosure-content">
              <dl class="app-fact-list">
                <div class="app-fact-list__item">
                  <dt>{{ t('data.snapshotId') }}</dt>
                  <dd>{{ snapshot.id }}</dd>
                </div>
                <div class="app-fact-list__item">
                  <dt>{{ t('projects.snapshots.parserVersion') }}</dt>
                  <dd>{{ snapshot.parser_version }}</dd>
                </div>
                <div class="app-fact-list__item">
                  <dt>{{ t('projects.snapshots.checksum') }}</dt>
                  <dd class="snapshot-hash">{{ snapshot.source_sha256 }}</dd>
                </div>
              </dl>
              <p class="snapshot-provenance-title">{{ t('data.configuration') }}</p>
              <pre>{{ JSON.stringify(snapshot.import_config ?? {}, null, 2) }}</pre>
            </div>
          </details>
        </div>
        <SnapshotRecords
          v-if="ready"
          :key="`${session.user?.id}:${snapshot.id}`"
          class="snapshot-detail-records"
          :project-id="projectId"
          :snapshot-id="snapshot.id"
          :record-count="snapshot.record_count ?? null"
        />
      </template>
    </template>
  </main>
</template>

<style scoped>
.snapshot-detail {
  container: snapshot-detail / inline-size;
}
.snapshot-summary {
  --app-fact-list-label-width: 8rem;
}
.snapshot-summary-status dd {
  font-weight: var(--weight-semibold);
}
.snapshot-summary-status--ready dd {
  color: var(--good);
}
.snapshot-summary-status--failed dd {
  color: var(--critical-text);
}
.snapshot-detail-feedback {
  margin-block-start: var(--space-4);
}
.snapshot-detail-records {
  margin-block-start: var(--space-8);
}
.snapshot-review-stats {
  margin-block-start: var(--space-6);
}
.snapshot-review-stats-note {
  margin: 0 0 var(--space-4);
  color: var(--text-secondary);
}
.snapshot-secondary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  margin-block-start: var(--space-6);
  align-items: start;
}
.snapshot-disclosure {
  min-inline-size: 0;
}
.snapshot-disclosure[open] {
  grid-column: 1 / -1;
}
.snapshot-disclosure summary {
  min-block-size: var(--control-min-size);
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  font-weight: var(--weight-semibold);
  align-content: center;
}
.snapshot-disclosure-count {
  margin-inline-start: var(--space-2);
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  font-weight: var(--weight-regular);
}
.snapshot-disclosure-content {
  padding: var(--space-1) var(--space-4) var(--space-4);
}
.snapshot-disclosure-empty {
  margin: 0;
  color: var(--text-secondary);
}
.snapshot-source-table {
  inline-size: 100%;
  border-collapse: collapse;
  text-align: start;
}
.snapshot-source-table th,
.snapshot-source-table td {
  padding: var(--space-2) var(--space-3);
  border-block-end: 1px solid var(--border);
  vertical-align: top;
  text-align: start;
  overflow-wrap: anywhere;
}
.snapshot-source-table th {
  font-weight: var(--weight-semibold);
}
.snapshot-source-table td {
  font-variant-numeric: tabular-nums;
}
.snapshot-source-table .snapshot-hash {
  min-inline-size: 13rem;
}
.snapshot-hash {
  font-family: var(--font-mono);
  font-size: var(--font-size-small);
}
.snapshot-provenance dl {
  margin-block-end: var(--space-5);
}
.snapshot-provenance-title {
  margin: 0 0 var(--space-3);
  font-weight: var(--weight-semibold);
}
.snapshot-provenance pre {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: var(--font-size-small);
}
@container snapshot-detail (width < 40rem) {
  .snapshot-secondary {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
