<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppProgress from '@/components/base/AppProgress.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { hasProjectRole } from '@/features/projects/projectRoles'
import { useProject } from '@/features/projects/useProjects'
import { useImportedSnapshot } from '@/features/projects/useSnapshotData'

import AggregationSection from './AggregationSection.vue'
import ExecutionCard from './ExecutionCard.vue'
import RunProvenance from './RunProvenance.vue'
import { TERMINAL_RUN_STATUSES, useRun, useRunExecutions } from './useRunDetail'
import { useRunProgress } from './useRunProgress'
import { useStatusLabel } from './useStatusLabel'

const { t, d, n } = useI18n()
const label = useStatusLabel()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const snapshotId = useRouteParam('snapshotId')
const runId = useRouteParam('runId')

const project = useProject(projectId, isSignedIn)
const snapshot = useImportedSnapshot(projectId, snapshotId, isSignedIn)
const canRead = computed(
  () =>
    isSignedIn.value &&
    project.isSuccess.value &&
    project.data.value?.id === projectId.value &&
    hasProjectRole(project.data.value.current_user_role, 'viewer') &&
    snapshot.data.value?.id === snapshotId.value &&
    snapshot.data.value.project_id === projectId.value &&
    snapshot.data.value.status === 'ready',
)
const run = useRun(runId, canRead)
const selectedRun = computed(() => {
  const value = run.data.value
  return canRead.value &&
    run.isSuccess.value &&
    value?.id === runId.value &&
    value.dataset_snapshot_id === snapshotId.value
    ? value
    : undefined
})
const canReadExecutions = computed(() => selectedRun.value !== undefined)
const executions = useRunExecutions(runId, canReadExecutions)

// A finished run has nothing left to stream; opening it reads the persisted state only.
const isLive = computed(
  () => selectedRun.value !== undefined && !TERMINAL_RUN_STATUSES.has(selectedRun.value.status),
)
const { state: streamState } = useRunProgress(runId, isLive)

const isTerminalRun = computed(
  () => selectedRun.value !== undefined && TERMINAL_RUN_STATUSES.has(selectedRun.value.status),
)
const outcomeFirst = computed(
  () =>
    selectedRun.value?.status === 'completed' ||
    selectedRun.value?.status === 'completed_with_errors',
)
const executionIssueCount = computed(() =>
  (executions.data.value ?? []).reduce(
    (count, execution) =>
      count +
      (execution.status === 'failed' || execution.status === 'completed_with_errors' ? 1 : 0),
    0,
  ),
)

const statusLabel = computed(() => label(run.data.value?.status ?? ''))

const connectionLabel = computed(() => {
  switch (streamState.value) {
    case 'connecting':
      return t('runs.detail.connection.connecting')
    case 'live':
      return t('runs.detail.connection.live')
    case 'reconnecting':
      return t('runs.detail.connection.reconnecting')
  }
  return ''
})

function retryContext(): void {
  void project.refetch()
  void snapshot.refetch()
}
</script>

<template>
  <main class="run-detail app-page-frame">
    <header class="run-detail-heading-row app-page-heading">
      <div class="run-detail-heading-copy app-page-heading__copy">
        <h1 class="run-detail-title app-page-heading__title">
          {{
            selectedRun
              ? t('runs.detail.titleWithDate', {
                  date: d(new Date(selectedRun.created_at), 'timestamp'),
                })
              : t('runs.detail.title')
          }}
        </h1>
        <RouterLink
          v-if="snapshot.data.value"
          class="run-detail-dataset"
          :to="{ name: 'snapshotDetail', params: { projectId, snapshotId } }"
        >
          {{
            t('data.snapshotTitle', {
              date: d(new Date(snapshot.data.value.created_at), 'timestamp'),
            })
          }}
        </RouterLink>
      </div>
      <div v-if="selectedRun" class="app-page-heading__actions">
        <AppButton variant="ghost" :to="{ name: 'projectClassification', params: { projectId } }">
          {{ t('runs.changeSelection') }}
        </AppButton>
      </div>
    </header>
    <p
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      role="status"
    >
      {{ t('runs.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="run-detail-load-error app-card">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('runs.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <div
        v-if="project.isError.value || snapshot.isError.value"
        class="run-detail-load-error app-card"
      >
        <p role="alert">{{ t('runs.contextLoadError') }}</p>
        <AppButton variant="ghost" @click="retryContext">{{ t('runs.retry') }}</AppButton>
      </div>
      <p
        v-else-if="project.isPending.value || snapshot.isPending.value"
        class="app-card"
        role="status"
      >
        {{ t('runs.loading') }}
      </p>
      <div v-else-if="!canRead" class="run-detail-unavailable app-card">
        <p>{{ t('runs.contextUnavailable') }}</p>
        <RouterLink :to="{ name: 'projectClassification', params: { projectId } }">{{
          t('runs.changeSelection')
        }}</RouterLink>
      </div>
      <p v-else-if="run.isPending.value" class="app-card" role="status">
        {{ t('runs.loading') }}
      </p>
      <div v-else-if="run.isError.value" class="run-detail-load-error app-card">
        <p role="alert">{{ t('runs.detail.loadError') }}</p>
        <AppButton class="run-detail-retry" type="button" @click="() => run.refetch()">
          {{ t('runs.retry') }}
        </AppButton>
      </div>
      <template v-else-if="selectedRun">
        <div class="run-detail-overview app-card">
          <dl class="run-detail-summary">
            <div
              class="run-detail-summary-fact run-detail-summary-status"
              :class="`run-detail-summary-status--${selectedRun.status}`"
            >
              <dt>{{ t('runs.detail.status') }}</dt>
              <dd class="run-detail-status">{{ statusLabel }}</dd>
            </div>
            <div class="run-detail-summary-fact">
              <dt>{{ t('runs.detail.created') }}</dt>
              <dd>
                <time :datetime="selectedRun.created_at" class="run-detail-created">
                  {{ d(new Date(selectedRun.created_at), 'timestamp') }}
                </time>
              </dd>
            </div>
            <div v-if="selectedRun.progress.total != null" class="run-detail-summary-fact">
              <dt>{{ t('runs.detail.progress') }}</dt>
              <dd class="run-detail-counts">
                {{
                  t('runs.item.progressValue', {
                    completed: n(selectedRun.progress.completed, 'integer'),
                    total: n(selectedRun.progress.total, 'integer'),
                    failed: n(selectedRun.progress.failed, 'integer'),
                  })
                }}
              </dd>
            </div>
          </dl>
          <!-- Always in the DOM so assistive technology announces the change, not the mount. -->
          <span class="run-detail-connection" role="status">{{ connectionLabel }}</span>
          <AppProgress
            v-if="!isTerminalRun"
            :percentage="selectedRun.progress.percentage ?? null"
            :label="t('runs.detail.overallProgressLabel')"
          />
          <div
            v-if="selectedRun.failure_class || selectedRun.failure_diagnostic"
            class="run-detail-failure"
          >
            <p v-if="selectedRun.failure_class" class="run-detail-failure-class">
              {{ selectedRun.failure_class }}
            </p>
            <p v-if="selectedRun.failure_diagnostic">
              {{ selectedRun.failure_diagnostic }}
            </p>
          </div>
        </div>

        <AggregationSection
          v-if="executions.data.value && outcomeFirst"
          :key="`outcome:${runId}`"
          :project-id="projectId"
          :run="selectedRun"
          :executions="executions.data.value"
        />

        <div class="run-detail-actions app-card">
          <RouterLink
            class="run-detail-evaluations"
            :to="{ name: 'evaluations', params: { projectId, runId } }"
          >
            {{ t('runs.detail.evaluations') }}
          </RouterLink>

          <RouterLink
            class="run-detail-evaluations run-detail-exports"
            :to="{ name: 'exports', params: { projectId, runId } }"
          >
            {{ t('runs.detail.exports') }}
          </RouterLink>
        </div>

        <section class="run-detail-executions" aria-labelledby="run-executions-heading">
          <div class="run-detail-section-heading">
            <h2 id="run-executions-heading" class="run-detail-heading">
              {{ t('runs.detail.executions') }}
            </h2>
            <p v-if="isTerminalRun && executions.data.value" class="run-detail-execution-summary">
              {{
                executionIssueCount
                  ? t('runs.detail.methodCountWithIssues', {
                      count: n(executions.data.value.length, 'integer'),
                      issues: n(executionIssueCount, 'integer'),
                    })
                  : t('runs.detail.methodCount', {
                      count: n(executions.data.value.length, 'integer'),
                    })
              }}
            </p>
          </div>
          <p v-if="executions.isPending.value" class="app-card" role="status">
            {{ t('runs.loading') }}
          </p>
          <div v-else-if="executions.isError.value" class="run-detail-load-error app-card">
            <p role="alert">{{ t('runs.detail.executionsLoadError') }}</p>
            <AppButton
              class="run-detail-executions-retry"
              type="button"
              @click="() => executions.refetch()"
            >
              {{ t('runs.retry') }}
            </AppButton>
          </div>
          <p
            v-else-if="(executions.data.value ?? []).length === 0"
            class="run-detail-empty app-card"
          >
            {{ t('runs.detail.noExecutions') }}
          </p>
          <ul v-else class="run-detail-execution-list">
            <ExecutionCard
              v-for="execution in executions.data.value"
              :key="execution.id"
              :execution="execution"
              :compact="isTerminalRun"
              :results-to="{
                name: 'methodExecutionResults',
                params: { projectId, snapshotId, runId, executionId: execution.id },
              }"
            />
          </ul>
        </section>

        <AggregationSection
          v-if="executions.data.value && !outcomeFirst"
          :key="`follow-up:${runId}`"
          :project-id="projectId"
          :run="selectedRun"
          :executions="executions.data.value"
        />
        <RunProvenance :run="selectedRun" />
      </template>
      <div v-else class="run-detail-unavailable app-card">
        <p>{{ t('runs.contextUnavailable') }}</p>
        <RouterLink :to="{ name: 'projectClassification', params: { projectId } }">{{
          t('runs.changeSelection')
        }}</RouterLink>
      </div>
    </template>
  </main>
</template>

<style scoped>
.run-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.run-detail > * {
  max-width: 100%;
}

.run-detail-actions,
.run-detail-section-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3) var(--space-6);
}

.run-detail-heading-row {
  inline-size: 100%;
  margin-block-end: 0;
}

.run-detail-heading-copy {
  display: grid;
  gap: var(--space-1);
}

.run-detail-dataset,
.run-detail-evaluations,
.run-detail-unavailable a {
  color: var(--accent);
  font-weight: var(--weight-semibold);
  text-underline-offset: 0.2em;
}

.run-detail-dataset {
  width: fit-content;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: var(--weight-regular);
}

.run-detail-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.run-detail-load-error p,
.run-detail-failure {
  margin: 0;
  color: var(--critical-text);
}

.run-detail-failure p {
  margin: 0;
}

.run-detail-failure-class {
  font-weight: var(--weight-semibold);
}

.run-detail-overview {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.run-detail-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3) var(--space-8);
  margin: 0;
}

.run-detail-summary-fact {
  display: grid;
  gap: var(--space-1);
}

.run-detail-summary dt {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.run-detail-summary dd {
  margin: 0;
}

.run-detail-status {
  font-weight: var(--weight-semibold);
}

.run-detail-summary-status--completed {
  color: var(--good);
}

.run-detail-summary-status--failed,
.run-detail-summary-status--completed_with_errors {
  color: var(--critical-text);
}

.run-detail-created,
.run-detail-counts,
.run-detail-empty,
.run-detail-execution-summary {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.run-detail-connection,
.run-detail-execution-summary {
  margin: 0;
}

.run-detail-executions {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: var(--space-3);
}

.run-detail-heading {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.run-detail-execution-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
