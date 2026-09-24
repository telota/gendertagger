<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useRunExecutions } from '@/features/runs/useRunDetail'
import { useStatusLabel } from '@/features/runs/useStatusLabel'

import AccuracyTable from './AccuracyTable.vue'
import ConfusionMatrices from './ConfusionMatrices.vue'
import CoverageTable from './CoverageTable.vue'
import EnsemblePanel from './EnsemblePanel.vue'
import KappaMatrix from './KappaMatrix.vue'
import { ReportShapeError } from './reportSchema'
import { useEvaluation, useEvaluationReport } from './useEvaluations'

const { t, d, n } = useI18n()
const label = useStatusLabel()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')
const evaluationId = useRouteParam('evaluationId')

const evaluation = useEvaluation(evaluationId, isSignedIn)
const executions = useRunExecutions(runId, isSignedIn)

const isCompleted = computed(() => evaluation.data.value?.status === 'completed')
const report = useEvaluationReport(evaluationId, isCompleted)

// The report is an immutable artifact; what produced it is on the evaluation itself.
const selection = computed(() => {
  const byId = new Map((executions.data.value ?? []).map((execution) => [execution.id, execution]))
  return (evaluation.data.value?.method_execution_ids ?? []).map((id) => ({
    id,
    execution: byId.get(id) ?? null,
  }))
})

const resolvedConfig = computed(() =>
  JSON.stringify(evaluation.data.value?.resolved_config ?? {}, null, 2),
)
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
  <main class="evaluation-detail">
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('runs.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="evaluation-detail-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('runs.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <RouterLink
        class="evaluation-detail-back"
        :to="{ name: 'evaluations', params: { projectId, runId } }"
      >
        {{ t('evaluation.detail.backToList') }}
      </RouterLink>

      <p v-if="evaluation.isPending.value" role="status">{{ t('runs.loading') }}</p>
      <div v-else-if="evaluation.isError.value" class="evaluation-detail-load-error">
        <p role="alert">{{ t('evaluation.detail.loadError') }}</p>
        <AppButton
          class="evaluation-detail-retry"
          type="button"
          @click="() => evaluation.refetch()"
        >
          {{ t('runs.retry') }}
        </AppButton>
      </div>
      <template v-else-if="evaluation.data.value">
        <h1 class="evaluation-detail-title">{{ t('evaluation.detail.title') }}</h1>
        <p class="evaluation-detail-status" role="status">
          <span :class="`evaluation-detail-status--${evaluation.data.value.status}`">{{
            label(evaluation.data.value.status)
          }}</span>
        </p>
        <div
          v-if="evaluation.data.value.failure_class || evaluation.data.value.failure_diagnostic"
          class="evaluation-detail-failure"
        >
          <p v-if="evaluation.data.value.failure_class" class="evaluation-detail-failure-class">
            {{ evaluation.data.value.failure_class }}
          </p>
          <p v-if="evaluation.data.value.failure_diagnostic">
            {{ evaluation.data.value.failure_diagnostic }}
          </p>
        </div>

        <section class="evaluation-detail-block" aria-labelledby="evaluation-provenance-heading">
          <h2 id="evaluation-provenance-heading" class="evaluation-detail-heading">
            {{ t('evaluation.detail.provenance') }}
          </h2>
          <dl class="evaluation-detail-facts">
            <div class="evaluation-detail-fact">
              <dt>{{ t('evaluation.item.definition') }}</dt>
              <dd>{{ evaluation.data.value.definition ?? '' }}</dd>
            </div>
            <div class="evaluation-detail-fact">
              <dt>{{ t('evaluation.item.configHash') }}</dt>
              <dd>
                <code class="evaluation-detail-hash">{{
                  evaluation.data.value.config_sha256
                }}</code>
              </dd>
            </div>
            <div class="evaluation-detail-fact">
              <dt>{{ t('aggregations.detail.created') }}</dt>
              <dd>{{ d(new Date(evaluation.data.value.created_at), 'timestamp') }}</dd>
            </div>
            <div v-if="evaluation.data.value.finished_at" class="evaluation-detail-fact">
              <dt>{{ t('aggregations.detail.finished') }}</dt>
              <dd>{{ d(new Date(evaluation.data.value.finished_at), 'timestamp') }}</dd>
            </div>
            <div
              v-if="evaluation.data.value.aggregation_execution_id"
              class="evaluation-detail-fact"
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
          <details class="evaluation-detail-config">
            <summary>{{ t('evaluation.detail.resolvedConfig') }}</summary>
            <pre class="evaluation-detail-config-json">{{ resolvedConfig }}</pre>
          </details>
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
                <template v-if="entry.execution">
                  <span class="evaluation-detail-method">{{ entry.execution.method_name }}</span>
                  {{ entry.execution.implementation_version }}
                </template>
                <code v-else>{{ entry.id }}</code>
              </li>
            </ul>
          </details>
          <a v-if="isCompleted" class="evaluation-detail-download" :href="downloadUrl" download>
            {{ t('evaluation.detail.download') }}
          </a>
        </section>

        <p
          v-if="!isCompleted && !['failed', 'cancelled'].includes(evaluation.data.value.status)"
          class="evaluation-detail-waiting"
          role="status"
        >
          {{ t('evaluation.detail.waiting') }}
        </p>

        <template v-if="isCompleted">
          <p v-if="report.isPending.value" role="status">{{ t('runs.loading') }}</p>
          <div v-else-if="report.isError.value" class="evaluation-detail-load-error">
            <p role="alert" class="evaluation-detail-report-error">{{ reportError }}</p>
            <AppButton
              class="evaluation-detail-report-retry"
              type="button"
              @click="() => report.refetch()"
            >
              {{ t('runs.retry') }}
            </AppButton>
          </div>
          <template v-else-if="report.data.value">
            <section class="evaluation-detail-block" aria-labelledby="evaluation-benchmark-heading">
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

.evaluation-detail-title {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
}

.evaluation-detail-status {
  margin: 0;
  font-weight: var(--weight-semibold);
}

.evaluation-detail-status--completed {
  color: var(--good);
}

.evaluation-detail-status--failed {
  color: var(--critical);
}

.evaluation-detail-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.evaluation-detail-load-error p,
.evaluation-detail-failure {
  margin: 0;
  color: var(--critical);
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

.evaluation-detail-facts {
  display: grid;
  gap: var(--space-2);
  margin: 0;
}

.evaluation-detail-fact {
  display: grid;
  grid-template-columns: 9rem 1fr;
  gap: var(--space-3);
}

.evaluation-detail-fact dt {
  color: var(--text-secondary);
}

.evaluation-detail-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.evaluation-detail-hash {
  font-size: var(--font-size-small);
}

.evaluation-detail-aggregation,
.evaluation-detail-download {
  align-self: flex-start;
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.evaluation-detail-config summary,
.evaluation-detail-selection summary {
  cursor: pointer;
  font-weight: var(--weight-semibold);
}

.evaluation-detail-config-json {
  margin: var(--space-2) 0 0;
  padding: var(--space-3);
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
  font-size: var(--font-size-small);
}

.evaluation-detail-methods {
  margin: var(--space-2) 0 0;
  padding-left: var(--space-4);
  font-size: var(--font-size-small);
}

.evaluation-detail-method {
  font-weight: var(--weight-semibold);
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
