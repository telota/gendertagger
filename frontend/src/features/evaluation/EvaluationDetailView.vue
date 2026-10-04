<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useArtifactRouteContext } from '@/composables/useArtifactRouteContext'
import { useRunExecutions } from '@/composables/useRunDetail'
import LifecycleStatus from '@/components/domain/LifecycleStatus.vue'
import JsonData from '@/components/domain/JsonData.vue'
import SelectedExecution from '@/components/domain/SelectedExecution.vue'
import ProvenanceValue from '@/components/domain/ProvenanceValue.vue'

import AccuracyTable from './AccuracyTable.vue'
import ConfusionMatrices from './ConfusionMatrices.vue'
import CoverageTable from './CoverageTable.vue'
import EnsemblePanel from './EnsemblePanel.vue'
import KappaMatrix from './KappaMatrix.vue'
import { ReportShapeError } from './reportSchema'
import { useEvaluation, useEvaluationReport } from './useEvaluations'

const { t, d, n } = useI18n()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')
const evaluationId = useRouteParam('evaluationId')

const query = useEvaluation(evaluationId, isSignedIn)
const context = useArtifactRouteContext(evaluationId, query)
const evaluation = { ...query, ...context }
const executions = useRunExecutions(runId, context.valid)

const isCompleted = computed(
  () => isSignedIn.value && evaluation.data.value?.status === 'completed',
)
const report = useEvaluationReport(evaluationId, isCompleted)

// The report is an immutable artifact; what produced it is on the evaluation itself.
const selection = computed(() => {
  const byId = new Map((executions.data.value ?? []).map((execution) => [execution.id, execution]))
  return (evaluation.data.value?.method_execution_ids ?? []).map((id) => ({
    id,
    execution: byId.get(id) ?? null,
  }))
})

const confidenceLevel = computed<number | null>(() => {
  const value = evaluation.data.value?.resolved_config?.['confidence_level']
  return typeof value === 'number' ? value : null
})

const reportError = computed(() =>
  report.error.value instanceof ReportShapeError
    ? t('evaluation.report.shapeError')
    : t('evaluation.report.loadError'),
)
const downloadUrl = computed(() => `/api/v1/evaluations/${evaluationId.value}/report`)
</script>

<template>
  <main class="evaluation-detail app-page-frame">
    <RouterLink
      v-if="context.valid.value"
      class="evaluation-detail-back"
      :to="{ name: 'evaluations', params: { projectId, runId } }"
    >
      {{ t('evaluation.detail.backToList') }}
    </RouterLink>
    <header class="evaluation-detail-page-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="evaluation-detail-title app-page-heading__title">
          {{ t('evaluation.detail.title') }}
        </h1>
        <p
          v-if="isSignedIn && evaluation.data.value"
          class="evaluation-detail-status"
          role="status"
        >
          <LifecycleStatus :status="evaluation.data.value.status" />
        </p>
      </div>
      <div v-if="isCompleted" class="app-page-heading__actions">
        <a class="evaluation-detail-download" :href="downloadUrl" download>
          {{ t('evaluation.detail.download') }}
        </a>
      </div>
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
        <AppButton type="button" variant="ghost" @click="retrySession">
          {{ t('runs.retry') }}
        </AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <AppFeedback v-if="evaluation.isPending.value" class="app-card" announcement="polite">
        {{ t('runs.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="evaluation.isError.value"
        class="app-card"
        announcement="assertive"
        tone="critical"
      >
        {{ t('evaluation.detail.loadError') }}
        <template #actions>
          <AppButton
            class="evaluation-detail-retry"
            type="button"
            variant="ghost"
            :disabled="evaluation.isFetching.value"
            @click="() => evaluation.refetch()"
          >
            {{ t('runs.retry') }}
          </AppButton>
        </template>
      </AppFeedback>
      <template v-else-if="evaluation.data.value">
        <div
          v-if="evaluation.data.value.failure_class || evaluation.data.value.failure_diagnostic"
          class="evaluation-detail-failure app-card"
        >
          <p v-if="evaluation.data.value.failure_class" class="evaluation-detail-failure-class">
            {{ evaluation.data.value.failure_class }}
          </p>
          <p v-if="evaluation.data.value.failure_diagnostic">
            {{ evaluation.data.value.failure_diagnostic }}
          </p>
        </div>

        <section
          class="evaluation-detail-block app-card"
          aria-labelledby="evaluation-provenance-heading"
        >
          <h2 id="evaluation-provenance-heading" class="evaluation-detail-heading">
            {{ t('evaluation.detail.provenance') }}
          </h2>
          <dl class="evaluation-detail-facts app-fact-list">
            <div class="evaluation-detail-fact app-fact-list__item">
              <dt>{{ t('evaluation.item.definition') }}</dt>
              <dd>{{ evaluation.data.value.definition ?? '' }}</dd>
            </div>
            <div class="evaluation-detail-fact app-fact-list__item">
              <dt>{{ t('evaluation.item.configHash') }}</dt>
              <dd>
                <ProvenanceValue :value="evaluation.data.value.config_sha256" />
              </dd>
            </div>
            <div class="evaluation-detail-fact app-fact-list__item">
              <dt>{{ t('aggregations.detail.created') }}</dt>
              <dd>{{ d(new Date(evaluation.data.value.created_at), 'timestamp') }}</dd>
            </div>
            <div
              v-if="evaluation.data.value.finished_at"
              class="evaluation-detail-fact app-fact-list__item"
            >
              <dt>{{ t('aggregations.detail.finished') }}</dt>
              <dd>{{ d(new Date(evaluation.data.value.finished_at), 'timestamp') }}</dd>
            </div>
            <div
              v-if="evaluation.data.value.aggregation_execution_id"
              class="evaluation-detail-fact app-fact-list__item"
            >
              <dt>{{ t('evaluation.detail.aggregation') }}</dt>
              <dd>
                <RouterLink
                  class="evaluation-detail-aggregation"
                  :to="{
                    name: 'aggregationDetail',
                    params: {
                      projectId,
                      runId,
                      aggregationId: evaluation.data.value.aggregation_execution_id,
                    },
                  }"
                >
                  {{ t('evaluation.detail.openAggregation') }}
                </RouterLink>
              </dd>
            </div>
          </dl>
          <JsonData
            :value="evaluation.data.value.resolved_config"
            :summary="t('evaluation.detail.resolvedConfig')"
            ruled
          />
          <details class="evaluation-detail-selection">
            <summary>
              {{
                t('evaluation.detail.selection', {
                  count: n(selection.length, 'integer'),
                })
              }}
            </summary>
            <ul class="evaluation-detail-methods">
              <li v-for="entry in selection" :key="entry.id">
                <SelectedExecution :id="entry.id" :execution="entry.execution" />
              </li>
            </ul>
          </details>
        </section>

        <p
          v-if="!isCompleted && !['failed', 'cancelled'].includes(evaluation.data.value.status)"
          class="evaluation-detail-waiting app-card"
          role="status"
        >
          {{ t('evaluation.detail.waiting') }}
        </p>

        <template v-if="isCompleted">
          <AppFeedback v-if="report.isPending.value" class="app-card" announcement="polite">
            {{ t('runs.loading') }}
          </AppFeedback>
          <AppFeedback
            v-else-if="report.isError.value"
            class="app-card"
            announcement="assertive"
            tone="critical"
          >
            <p class="evaluation-detail-report-error">{{ reportError }}</p>
            <template #actions>
              <AppButton
                class="evaluation-detail-report-retry"
                type="button"
                variant="ghost"
                :disabled="report.isFetching.value"
                @click="() => report.refetch()"
              >
                {{ t('runs.retry') }}
              </AppButton>
            </template>
          </AppFeedback>
          <template v-else-if="report.data.value">
            <section
              class="evaluation-detail-block app-card"
              aria-labelledby="evaluation-benchmark-heading"
            >
              <h2 id="evaluation-benchmark-heading" class="evaluation-detail-heading">
                {{ t('evaluation.report.benchmark.title') }}
              </h2>
              <p class="evaluation-detail-benchmark">
                {{
                  t('evaluation.report.benchmark.text', {
                    method: report.data.value.benchmark.method_name,
                    size: n(report.data.value.benchmark.size, 'integer'),
                  })
                }}
              </p>
              <ul class="evaluation-detail-classes">
                <li
                  v-for="benchmarkLabel in report.data.value.benchmark.labels"
                  :key="benchmarkLabel"
                >
                  <span class="evaluation-detail-token">{{ benchmarkLabel }}</span>
                  {{ n(report.data.value.benchmark.class_counts[benchmarkLabel] ?? 0, 'integer') }}
                </li>
              </ul>
            </section>

            <CoverageTable :rows="report.data.value.coverage" />
            <AccuracyTable
              :rows="report.data.value.accuracy"
              :benchmark="report.data.value.benchmark"
              :confidence-level="confidenceLevel"
            />
            <ConfusionMatrices
              :rows="report.data.value.accuracy"
              :benchmark="report.data.value.benchmark"
            />
            <KappaMatrix :cells="report.data.value.kappa_matrix" />
            <EnsemblePanel :ensemble="report.data.value.ensemble" />
          </template>
        </template>
      </template>
    </template>
  </main>
</template>

<style scoped>
.evaluation-detail {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-5, var(--space-4));
}

.evaluation-detail > * {
  max-width: 100%;
}

.evaluation-detail-back {
  align-self: flex-start;
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.evaluation-detail-page-heading {
  margin-block-end: 0;
}

.evaluation-detail-status {
  margin: 0;
  font-weight: var(--weight-semibold);
}

.evaluation-detail-failure {
  margin: 0;
  color: var(--critical-text);
}

.evaluation-detail-failure p {
  margin: 0;
}

.evaluation-detail-failure-class {
  font-weight: var(--weight-semibold);
}

.evaluation-detail-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.evaluation-detail-heading {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.evaluation-detail-aggregation,
.evaluation-detail-download {
  display: inline-flex;
  min-block-size: var(--control-min-size);
  align-items: center;
  padding-inline: var(--space-2);
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.evaluation-detail-selection summary {
  cursor: pointer;
  font-weight: var(--weight-semibold);
}

.evaluation-detail-methods {
  margin: var(--space-2) 0 0;
  padding-left: var(--space-4);
  font-size: var(--font-size-small);
}

.evaluation-detail-waiting,
.evaluation-detail-benchmark {
  margin: 0;
  color: var(--text-secondary);
}

.evaluation-detail-classes {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}

.evaluation-detail-token {
  margin-right: var(--space-1);
  font-family: var(--font-mono, ui-monospace, monospace);
}
</style>
