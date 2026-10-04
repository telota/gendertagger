<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useDebouncedValue } from '@/composables/useDebouncedValue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { hasProjectRole } from '@/composables/projectRoles'
import { useProject } from '@/composables/useProjects'
import { useImportedSnapshot } from '@/composables/useSnapshotData'
import PredictionDecision from '@/components/domain/PredictionDecision.vue'
import PredictionStatus from '@/components/domain/PredictionStatus.vue'
import { useVocabularyGloss } from '@/composables/useVocabulary'
import type { components } from '@/api/schema'

import {
  TERMINAL_METHOD_EXECUTION_STATUSES,
  useRun,
  useRunExecutions,
} from '@/composables/useRunDetail'
import { useMethodExecutionResults, type MethodExecutionResult } from './useMethodExecutionResults'

const { t, d, n } = useI18n()
const gloss = useVocabularyGloss()
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

function labelGloss(label: components['schemas']['CanonicalLabel'] | null | undefined): string {
  return label ? gloss.label(label) : ''
}

function stateGloss(state: components['schemas']['MethodExecutionResultState']): string {
  return state === 'missing' ? t('runs.results.missing') : gloss.prediction(state)
}

function retryContext(): void {
  void project.refetch()
  void snapshot.refetch()
}
</script>

<template>
  <main class="method-results app-page-frame app-page-frame--wide">
    <header class="method-results-page-heading app-page-heading">
      <h1 class="method-results-title app-page-heading__title">
        {{ t('runs.results.title') }}
      </h1>
    </header>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      announcement="polite"
    >
      {{ t('runs.loading') }}
    </AppFeedback>
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('projects.sessionLoadError') }}
      <template #actions>
        <AppButton variant="ghost" @click="retrySession">{{ t('runs.retry') }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <AppFeedback
        v-if="project.isError.value || snapshot.isError.value"
        class="app-card"
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
        class="app-card"
        announcement="polite"
      >
        {{ t('runs.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="!canReadContext"
        class="app-card"
        announcement="assertive"
        tone="critical"
      >
        {{ t('runs.contextUnavailable') }}
        <template #actions>
          <AppButton variant="ghost" :to="{ name: 'projectClassification', params: { projectId } }">
            {{ t('runs.changeSelection') }}
          </AppButton>
        </template>
      </AppFeedback>
      <AppFeedback v-else-if="run.isPending.value" class="app-card" announcement="polite">
        {{ t('runs.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="run.isError.value || !selectedRun"
        class="app-card"
        announcement="assertive"
        tone="critical"
      >
        {{ t('runs.detail.loadError') }}
        <template #actions>
          <AppButton variant="ghost" @click="run.refetch()">{{ t('runs.retry') }}</AppButton>
        </template>
      </AppFeedback>
      <template v-else>
        <AppFeedback v-if="executions.isPending.value" class="app-card" announcement="polite">
          {{ t('runs.loading') }}
        </AppFeedback>
        <AppFeedback
          v-else-if="executions.isError.value"
          class="app-card"
          announcement="assertive"
          tone="critical"
        >
          {{ t('runs.detail.executionsLoadError') }}
          <template #actions>
            <AppButton variant="ghost" @click="executions.refetch()">{{
              t('runs.retry')
            }}</AppButton>
          </template>
        </AppFeedback>
        <AppFeedback
          v-else-if="!execution"
          class="app-card"
          announcement="assertive"
          tone="critical"
        >
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
        <AppFeedback v-else-if="!hasFinalResults" class="app-card" announcement="polite">
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
          <div class="method-results-content app-card">
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
              <AppTextField
                id="method-results-search"
                v-model="searchInput"
                type="search"
                :label="t('runs.results.search')"
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
                        <PredictionDecision
                          :prediction="item.prediction"
                          :gloss="labelGloss(item.prediction?.label)"
                          :missing="item.result_state === 'missing'"
                          method
                        />
                      </td>
                      <td>
                        <PredictionStatus
                          :status="item.result_state"
                          :gloss="stateGloss(item.result_state)"
                          display="badge"
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
          </div>
        </template>
      </template>
    </template>
  </main>
</template>

<style scoped>
.method-results {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-5);
}

.method-results > * {
  max-inline-size: 100%;
}

.method-results-content {
  display: flex;
  inline-size: 100%;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-5);
}

.method-results-content > * {
  max-inline-size: 100%;
}

.method-results-back {
  align-self: flex-start;
  color: var(--accent);
  font-weight: var(--weight-semibold);
  text-underline-offset: 0.2em;
}

.method-results-heading {
  display: grid;
  gap: var(--space-2);
}

.method-results-page-heading {
  inline-size: 100%;
  margin-block-end: 0;
}

.method-results-heading p,
.method-results-note,
.method-results-empty,
.method-results-confidence-note {
  margin: 0;
}

.method-results-heading p,
.method-results-note,
.method-results-empty,
.method-results-confidence-note {
  color: var(--text-secondary);
}

.method-results-heading p {
  max-inline-size: 70ch;
}

.method-results-note {
  max-inline-size: 74ch;
}

.method-results-search {
  --field-gap: var(--space-2);
  --field-label-size: inherit;
  --field-label-color: var(--text-primary);
  --field-control-width: 100%;
  display: grid;
  gap: var(--space-2);
  inline-size: min(100%, 34rem);
}

.method-results-search :deep(input) {
  padding: var(--space-2);
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

.method-results-confidence-note {
  max-inline-size: 74ch;
  font-size: var(--font-size-small);
}
</style>
