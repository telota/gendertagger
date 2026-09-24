<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppProgress from '@/components/base/AppProgress.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'

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

const run = useRun(runId, isSignedIn)
const executions = useRunExecutions(runId, isSignedIn)

// A finished run has nothing left to stream; opening it reads the persisted state only.
const isLive = computed(
  () => run.data.value !== undefined && !TERMINAL_RUN_STATUSES.has(run.data.value.status),
)
const { state: streamState } = useRunProgress(runId, isLive)

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
</script>

<template>
  <main class="run-detail">
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('runs.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="run-detail-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('runs.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <RouterLink
        class="run-detail-back"
        :to="{ name: 'snapshotRuns', params: { projectId, snapshotId } }"
      >
        {{ t('runs.detail.backToRuns') }}
      </RouterLink>

      <p v-if="run.isPending.value" role="status">{{ t('runs.loading') }}</p>
      <div v-else-if="run.isError.value" class="run-detail-load-error">
        <p role="alert">{{ t('runs.detail.loadError') }}</p>
        <AppButton class="run-detail-retry" type="button" @click="() => run.refetch()">
          {{ t('runs.retry') }}
        </AppButton>
      </div>
      <template v-else-if="run.data.value">
        <h1 class="run-detail-title">{{ t('runs.detail.title') }}</h1>
        <div class="run-detail-summary">
          <span class="run-detail-status" :class="`run-detail-status--${run.data.value.status}`">{{
            statusLabel
          }}</span>
          <time :datetime="run.data.value.created_at" class="run-detail-created">{{
            d(new Date(run.data.value.created_at), 'timestamp')
          }}</time>
          <!-- Always in the DOM so assistive technology announces the change, not the mount. -->
          <span class="run-detail-connection" role="status">{{ connectionLabel }}</span>
        </div>

        <AppProgress
          :percentage="run.data.value.progress.percentage ?? null"
          :label="t('runs.detail.overallProgressLabel')"
        />
        <p v-if="run.data.value.progress.total != null" class="run-detail-counts">
          {{
            t('runs.item.progressValue', {
              completed: n(run.data.value.progress.completed, 'integer'),
              total: n(run.data.value.progress.total, 'integer'),
              failed: n(run.data.value.progress.failed, 'integer'),
            })
          }}
        </p>
        <div
          v-if="run.data.value.failure_class || run.data.value.failure_diagnostic"
          class="run-detail-failure"
        >
          <p v-if="run.data.value.failure_class" class="run-detail-failure-class">
            {{ run.data.value.failure_class }}
          </p>
          <p v-if="run.data.value.failure_diagnostic">
            {{ run.data.value.failure_diagnostic }}
          </p>
        </div>

        <RouterLink
          class="run-detail-evaluations"
          :to="{ name: 'evaluations', params: { projectId, runId } }"
        >
          {{ t('runs.detail.evaluations') }}
        </RouterLink>

        <RunProvenance :run="run.data.value" />

        <section class="run-detail-executions" aria-labelledby="run-executions-heading">
          <h2 id="run-executions-heading" class="run-detail-heading">
            {{ t('runs.detail.executions') }}
          </h2>
          <p v-if="executions.isPending.value" role="status">{{ t('runs.loading') }}</p>
          <div v-else-if="executions.isError.value" class="run-detail-load-error">
            <p role="alert">{{ t('runs.detail.executionsLoadError') }}</p>
            <AppButton
              class="run-detail-executions-retry"
              type="button"
              @click="() => executions.refetch()"
            >
              {{ t('runs.retry') }}
            </AppButton>
          </div>
          <p v-else-if="(executions.data.value ?? []).length === 0" class="run-detail-empty">
            {{ t('runs.detail.noExecutions') }}
          </p>
          <ul v-else class="run-detail-execution-list">
            <ExecutionCard
              v-for="execution in executions.data.value"
              :key="execution.id"
              :execution="execution"
            />
          </ul>
        </section>

        <AggregationSection
          v-if="executions.data.value"
          :project-id="projectId"
          :run="run.data.value"
          :executions="executions.data.value"
        />
      </template>
    </template>
  </main>
</template>

<style scoped>
.run-detail {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
  max-width: 48rem;
}

.run-detail > * {
  max-width: 100%;
}

.run-detail-evaluations {
  color: var(--accent);
  font-weight: var(--weight-semibold);
  text-underline-offset: 0.2em;
}

.run-detail-back {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.run-detail-title {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
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
  color: var(--critical);
}

.run-detail-failure p {
  margin: 0;
}

.run-detail-failure-class {
  font-weight: var(--weight-semibold);
}

.run-detail-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-4);
}

.run-detail-status {
  font-weight: var(--weight-semibold);
}

.run-detail-status--completed {
  color: var(--good);
}

.run-detail-status--failed,
.run-detail-status--completed_with_errors {
  color: var(--critical);
}

.run-detail-created,
.run-detail-connection,
.run-detail-counts,
.run-detail-empty {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.run-detail-counts {
  margin: 0;
}

.run-detail-executions {
  width: 100%;
}

.run-detail-heading {
  margin: 0 0 var(--space-4);
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
