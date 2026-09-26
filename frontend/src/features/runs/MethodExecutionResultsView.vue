<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import { useDebouncedValue } from '@/composables/useDebouncedValue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { hasProjectRole } from '@/features/projects/projectRoles'
import { useProject } from '@/features/projects/useProjects'
import { useImportedSnapshot } from '@/features/projects/useSnapshotData'
import VocabBadge from '@/features/review/VocabBadge.vue'

import { TERMINAL_METHOD_EXECUTION_STATUSES, useRun, useRunExecutions } from './useRunDetail'
import { useMethodExecutionResults, type MethodExecutionResult } from './useMethodExecutionResults'

const { t, d, n } = useI18n()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const snapshotId = useRouteParam('snapshotId')
const runId = useRouteParam('runId')
const executionId = useRouteParam('executionId')

const project = useProject(projectId, isSignedIn)
const snapshot = useImportedSnapshot(projectId, snapshotId, isSignedIn)
const canReadContext = computed(
  () =>
    isSignedIn.value &&
    project.isSuccess.value &&
    project.data.value?.id === projectId.value &&
    hasProjectRole(project.data.value.current_user_role, 'viewer') &&
    snapshot.data.value?.id === snapshotId.value &&
    snapshot.data.value.project_id === projectId.value &&
    snapshot.data.value.status === 'ready',
)
const run = useRun(runId, canReadContext)
const selectedRun = computed(() => {
  const value = run.data.value
  return canReadContext.value &&
    run.isSuccess.value &&
    value?.id === runId.value &&
    value.dataset_snapshot_id === snapshotId.value
    ? value
    : undefined
})
const executions = useRunExecutions(
  runId,
  computed(() => selectedRun.value !== undefined),
)
const execution = computed(() => {
  if (!selectedRun.value || !executions.isSuccess.value) return undefined
  const value = executions.data.value?.find((item) => item.id === executionId.value)
  return value?.run_id === runId.value ? value : undefined
})

const hasFinalResults = computed(
  () =>
    execution.value !== undefined && TERMINAL_METHOD_EXECUTION_STATUSES.has(execution.value.status),
)
const searchInput = ref('')
const search = useDebouncedValue(searchInput, 250)
const results = useMethodExecutionResults(runId, executionId, search, hasFinalResults)
const items = computed(
  () =>
    results.data.value?.pages
      .flatMap((page) => page.items)
      .filter(
        (item) =>
          item.method_execution_id === executionId.value &&
          item.dataset_snapshot_id === snapshotId.value,
      ) ?? [],
)

function displayName(item: MethodExecutionResult): string {
  const forenames = (item.forenames ?? []).join(' ')
  if (item.surname) return [item.surname, forenames].filter(Boolean).join(', ')
  return forenames || item.tei_id
}

function labelGloss(label: string | null | undefined): string {
  return label === 'unknown' ? t('review.gloss.label.unknown') : ''
}

function stateGloss(state: string): string {
  switch (state) {
    case 'success':
      return t('review.gloss.prediction.success')
    case 'abstain':
      return t('review.gloss.prediction.abstain')
    case 'error':
      return t('review.gloss.prediction.error')
    default:
      return t('runs.results.missing')
  }
}

function retryContext(): void {
  void project.refetch()
  void snapshot.refetch()
}
</script>

<template>
  <main class="method-results">
    <h1 class="method-results-title">{{ t('runs.results.title') }}</h1>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      announcement="polite"
    >
      {{ t('runs.loading') }}
    </AppFeedback>
    <AppFeedback v-else-if="session.status === 'error'" announcement="assertive" tone="critical">
      {{ t('projects.sessionLoadError') }}
      <template #actions>
        <AppButton variant="ghost" @click="retrySession">{{ t('runs.retry') }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <AppFeedback
        v-if="project.isError.value || snapshot.isError.value"
        announcement="assertive"
        tone="critical"
      >
        {{ t('runs.contextLoadError') }}
        <template #actions>
          <AppButton variant="ghost" @click="retryContext">{{ t('runs.retry') }}</AppButton>
        </template>
      </AppFeedback>
      <AppFeedback
        v-else-if="project.isPending.value || snapshot.isPending.value"
        announcement="polite"
      >
        {{ t('runs.loading') }}
      </AppFeedback>
      <AppFeedback v-else-if="!canReadContext" announcement="assertive" tone="critical">
        {{ t('runs.contextUnavailable') }}
        <template #actions>
          <AppButton variant="ghost" :to="{ name: 'projectClassification', params: { projectId } }">
            {{ t('runs.changeSelection') }}
          </AppButton>
        </template>
      </AppFeedback>
      <AppFeedback v-else-if="run.isPending.value" announcement="polite">
        {{ t('runs.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="run.isError.value || !selectedRun"
        announcement="assertive"
        tone="critical"
      >
        {{ t('runs.detail.loadError') }}
        <template #actions>
          <AppButton variant="ghost" @click="run.refetch()">{{ t('runs.retry') }}</AppButton>
        </template>
      </AppFeedback>
      <template v-else>
        <AppFeedback v-if="executions.isPending.value" announcement="polite">
          {{ t('runs.loading') }}
        </AppFeedback>
        <AppFeedback v-else-if="executions.isError.value" announcement="assertive" tone="critical">
          {{ t('runs.detail.executionsLoadError') }}
          <template #actions>
            <AppButton variant="ghost" @click="executions.refetch()">{{
              t('runs.retry')
            }}</AppButton>
          </template>
        </AppFeedback>
        <AppFeedback v-else-if="!execution" announcement="assertive" tone="critical">
          {{ t('runs.contextUnavailable') }}
          <template #actions>
            <AppButton
              variant="ghost"
              :to="{ name: 'runDetail', params: { projectId, snapshotId, runId } }"
            >
              {{ t('runs.results.backToRun') }}
            </AppButton>
          </template>
        </AppFeedback>
        <AppFeedback v-else-if="!hasFinalResults" announcement="polite">
          {{ t('runs.results.notFinal') }}
          <template #actions>
            <AppButton
              variant="ghost"
              :to="{ name: 'runDetail', params: { projectId, snapshotId, runId } }"
            >
              {{ t('runs.results.backToRun') }}
            </AppButton>
          </template>
        </AppFeedback>
        <template v-else>
          <RouterLink
            class="method-results-back"
            :to="{ name: 'runDetail', params: { projectId, snapshotId, runId } }"
          >
            {{ t('runs.results.backToRun') }}
          </RouterLink>
          <header class="method-results-heading">
            <p class="method-results-intro">
              {{ t('runs.results.intro', { method: execution.method_name }) }}
            </p>
            <p v-if="execution.progress.total != null">
              {{
                t('runs.item.progressValue', {
                  completed: n(execution.progress.completed, 'integer'),
                  total: n(execution.progress.total, 'integer'),
                  failed: n(execution.progress.failed, 'integer'),
                })
              }}
            </p>
            <p v-if="snapshot.data.value">
              {{
                t('data.snapshotTitle', {
                  date: d(new Date(snapshot.data.value.created_at), 'timestamp'),
                })
              }}
            </p>
          </header>

          <p class="method-results-note">{{ t('runs.results.distinction') }}</p>

          <form class="method-results-search" @submit.prevent>
            <label for="method-results-search">{{ t('runs.results.search') }}</label>
            <input
              id="method-results-search"
              v-model="searchInput"
              type="search"
              :placeholder="t('runs.results.searchHint')"
            />
          </form>

          <AppFeedback v-if="results.isPending.value && items.length === 0" announcement="polite">
            {{ t('runs.loading') }}
          </AppFeedback>
          <AppFeedback v-else-if="results.isError.value" announcement="assertive" tone="critical">
            {{ t('runs.results.loadError') }}
            <template #actions>
              <AppButton variant="ghost" @click="results.refetch()">{{
                t('runs.retry')
              }}</AppButton>
            </template>
          </AppFeedback>
          <template v-else>
            <p v-if="items.length === 0" class="method-results-empty" role="status">
              {{ t('runs.results.empty') }}
            </p>
            <AppScrollRegion
              v-else
              :label="t('layout.tableRegion', { label: t('runs.results.title') })"
            >
              <table class="method-results-table">
                <thead>
                  <tr>
                    <th scope="col">{{ t('runs.results.person') }}</th>
                    <th scope="col">{{ t('runs.results.teiId') }}</th>
                    <th scope="col">{{ t('runs.results.decision') }}</th>
                    <th scope="col">{{ t('runs.results.status') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in items" :key="item.person_record_id">
                    <th scope="row">{{ displayName(item) }}</th>
                    <td>
                      <code>{{ item.tei_id }}</code>
                    </td>
                    <td>
                      <VocabBadge
                        :value="item.prediction?.label"
                        :gloss="labelGloss(item.prediction?.label)"
                        kind="label"
                      />
                      <div
                        v-if="
                          item.prediction?.raw_label || item.prediction?.method_confidence != null
                        "
                        class="method-results-decision-detail"
                      >
                        <span v-if="item.prediction?.raw_label">
                          {{ t('runs.results.rawLabel', { label: item.prediction.raw_label }) }}
                        </span>
                        <span v-if="item.prediction?.method_confidence != null">
                          {{
                            t('runs.results.confidence', {
                              value: n(item.prediction.method_confidence, 'confidence'),
                            })
                          }}
                        </span>
                      </div>
                      <p v-else-if="item.result_state === 'missing'" class="method-results-missing">
                        {{ t('runs.results.noPrediction') }}
                      </p>
                    </td>
                    <td>
                      <VocabBadge
                        :value="item.result_state"
                        :gloss="stateGloss(item.result_state)"
                        kind="state"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </AppScrollRegion>
            <p class="method-results-confidence-note">{{ t('runs.results.confidenceNote') }}</p>
            <AppButton
              v-if="results.hasNextPage.value"
              variant="ghost"
              :disabled="results.isFetchingNextPage.value"
              @click="results.fetchNextPage()"
            >
              {{ t('runs.results.loadMore') }}
            </AppButton>
          </template>
        </template>
      </template>
    </template>
  </main>
</template>

<style scoped>
.method-results {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-5);
  inline-size: 100%;
  max-inline-size: 76rem;
  margin-inline: auto;
  padding: var(--space-8) var(--page-gutter);
}

.method-results > * {
  max-inline-size: 100%;
}

.method-results-back {
  color: var(--accent);
  font-weight: var(--weight-semibold);
  text-underline-offset: 0.2em;
}

.method-results-heading {
  display: grid;
  gap: var(--space-2);
}

.method-results-title,
.method-results-heading p,
.method-results-note,
.method-results-empty,
.method-results-confidence-note,
.method-results-missing {
  margin: 0;
}

.method-results-title {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
}

.method-results-heading p,
.method-results-note,
.method-results-empty,
.method-results-confidence-note,
.method-results-missing {
  color: var(--text-secondary);
}

.method-results-heading p {
  max-inline-size: 70ch;
}

.method-results-note {
  max-inline-size: 74ch;
}

.method-results-search {
  display: grid;
  gap: var(--space-2);
  inline-size: min(100%, 34rem);
}

.method-results-search input {
  min-inline-size: 0;
  padding: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
}

.method-results-table {
  inline-size: 100%;
  min-inline-size: 48rem;
  border-collapse: collapse;
}

.method-results-table th,
.method-results-table td {
  padding: var(--space-3);
  border-block-end: 1px solid var(--border);
  text-align: start;
  vertical-align: top;
  overflow-wrap: anywhere;
}

.method-results-table th {
  font-weight: var(--weight-semibold);
}

.method-results-table code {
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}

.method-results-decision-detail {
  display: grid;
  gap: var(--space-1);
  margin-block-start: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}

.method-results-missing {
  margin-block-start: var(--space-2);
  font-size: var(--font-size-small);
}

.method-results-confidence-note {
  max-inline-size: 74ch;
  font-size: var(--font-size-small);
}
</style>
