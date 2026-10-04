<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import LifecycleStatus from '@/components/domain/LifecycleStatus.vue'
import JsonData from '@/components/domain/JsonData.vue'
import SelectedExecution from '@/components/domain/SelectedExecution.vue'
import ProvenanceValue from '@/components/domain/ProvenanceValue.vue'

import RunProvenance from './RunProvenance.vue'
import { useAggregation } from '@/composables/useAggregations'
import { useArtifactRouteContext } from '@/composables/useArtifactRouteContext'
import { useRunExecutions } from '@/composables/useRunDetail'

const { t, d } = useI18n()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')
const aggregationId = useRouteParam('aggregationId')

const query = useAggregation(aggregationId, isSignedIn)
const context = useArtifactRouteContext(aggregationId, query)
const aggregation = { ...query, ...context }
const run = { data: context.run }
const executions = useRunExecutions(runId, context.valid)

// The selection is stored as execution ids; the reader wants method names and versions.
const selection = computed(() => {
  const byId = new Map((executions.data.value ?? []).map((execution) => [execution.id, execution]))
  return (aggregation.data.value?.method_execution_ids ?? []).map((id) => ({
    id,
    execution: byId.get(id) ?? null,
  }))
})
</script>

<template>
  <main class="aggregation-detail app-page-frame">
    <RouterLink
      v-if="isSignedIn && run.data.value"
      class="aggregation-detail-back"
      :to="{
        name: 'runDetail',
        params: { projectId, snapshotId: run.data.value.dataset_snapshot_id, runId },
      }"
    >
      {{ t('aggregations.detail.backToRun') }}
    </RouterLink>

    <header class="aggregation-detail-page-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="aggregation-detail-title app-page-heading__title">
          {{ t('aggregations.detail.title') }}
        </h1>
        <p
          v-if="isSignedIn && aggregation.data.value"
          class="aggregation-detail-status"
          role="status"
        >
          <LifecycleStatus :status="aggregation.data.value.status" />
        </p>
      </div>
      <div
        v-if="isSignedIn && aggregation.data.value?.status === 'completed'"
        class="aggregation-detail-actions app-page-heading__actions"
      >
        <AppButton
          class="aggregation-detail-review"
          variant="text"
          :to="{ name: 'review', params: { projectId, runId, aggregationId } }"
        >
          {{ t('aggregations.detail.review') }}
        </AppButton>
        <AppButton
          class="aggregation-detail-review aggregation-detail-people"
          variant="text"
          :to="{ name: 'people', params: { projectId, runId, aggregationId } }"
        >
          {{ t('aggregations.detail.people') }}
        </AppButton>
        <AppButton
          class="aggregation-detail-review aggregation-detail-export"
          variant="text"
          :to="{ name: 'exports', params: { projectId, runId } }"
        >
          {{ t('aggregations.detail.export') }}
        </AppButton>
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
      <AppFeedback v-if="aggregation.isPending.value" class="app-card" announcement="polite">
        {{ t('runs.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="aggregation.isError.value"
        class="app-card"
        announcement="assertive"
        tone="critical"
      >
        {{ t('aggregations.detail.loadError') }}
        <template #actions>
          <AppButton
            class="aggregation-detail-retry"
            type="button"
            variant="ghost"
            :disabled="aggregation.isFetching.value"
            @click="() => aggregation.refetch()"
          >
            {{ t('runs.retry') }}
          </AppButton>
        </template>
      </AppFeedback>
      <template v-else-if="aggregation.data.value">
        <div
          v-if="aggregation.data.value.failure_class || aggregation.data.value.failure_diagnostic"
          class="aggregation-detail-failure app-card"
        >
          <p v-if="aggregation.data.value.failure_class" class="aggregation-detail-failure-class">
            {{ aggregation.data.value.failure_class }}
          </p>
          <p v-if="aggregation.data.value.failure_diagnostic">
            {{ aggregation.data.value.failure_diagnostic }}
          </p>
        </div>

        <dl class="aggregation-detail-facts app-fact-list app-card">
          <div class="aggregation-detail-fact app-fact-list__item">
            <dt>{{ t('aggregations.item.strategy') }}</dt>
            <dd>{{ aggregation.data.value.strategy ?? '' }}</dd>
          </div>
          <div class="aggregation-detail-fact app-fact-list__item">
            <dt>{{ t('aggregations.detail.created') }}</dt>
            <dd>{{ d(new Date(aggregation.data.value.created_at), 'timestamp') }}</dd>
          </div>
          <div
            v-if="aggregation.data.value.started_at"
            class="aggregation-detail-fact app-fact-list__item"
          >
            <dt>{{ t('aggregations.detail.started') }}</dt>
            <dd>{{ d(new Date(aggregation.data.value.started_at), 'timestamp') }}</dd>
          </div>
          <div
            v-if="aggregation.data.value.finished_at"
            class="aggregation-detail-fact app-fact-list__item"
          >
            <dt>{{ t('aggregations.detail.finished') }}</dt>
            <dd>{{ d(new Date(aggregation.data.value.finished_at), 'timestamp') }}</dd>
          </div>
          <div class="aggregation-detail-fact app-fact-list__item">
            <dt>{{ t('aggregations.item.configHash') }}</dt>
            <dd>
              <ProvenanceValue :value="aggregation.data.value.config_sha256" />
            </dd>
          </div>
        </dl>

        <section
          class="aggregation-detail-block app-card"
          aria-labelledby="aggregation-config-heading"
        >
          <h2 id="aggregation-config-heading" class="aggregation-detail-heading">
            {{ t('aggregations.detail.resolvedConfig') }}
          </h2>
          <JsonData :value="aggregation.data.value.resolved_config" />
        </section>

        <section
          class="aggregation-detail-block app-card"
          aria-labelledby="aggregation-selection-heading"
        >
          <h2 id="aggregation-selection-heading" class="aggregation-detail-heading">
            {{ t('aggregations.detail.selection') }}
          </h2>
          <p class="aggregation-detail-hint">{{ t('aggregations.detail.selectionHint') }}</p>
          <ul class="aggregation-detail-selection">
            <li v-for="entry in selection" :key="entry.id" class="aggregation-detail-selected">
              <SelectedExecution :id="entry.id" :execution="entry.execution" show-status />
            </li>
          </ul>
        </section>

        <div v-if="run.data.value" class="aggregation-detail-block">
          <p class="aggregation-detail-hint">{{ t('aggregations.detail.provenanceHint') }}</p>
          <RunProvenance :run="run.data.value" />
        </div>
      </template>
    </template>
  </main>
</template>

<style scoped>
.aggregation-detail {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
}

.aggregation-detail-page-heading {
  inline-size: 100%;
  margin-block-end: 0;
}

.aggregation-detail-back {
  align-self: flex-start;
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.aggregation-detail-review {
  color: var(--accent);
  font-weight: var(--weight-semibold);
  text-underline-offset: 0.2em;
}

.aggregation-detail-failure {
  margin: 0;
  color: var(--critical-text);
}

.aggregation-detail-failure p {
  margin: 0;
}

.aggregation-detail-failure-class {
  font-weight: var(--weight-semibold);
}

.aggregation-detail-status {
  margin: 0;
  font-weight: var(--weight-semibold);
}

.aggregation-detail-facts {
  inline-size: 100%;
}

.aggregation-detail-block {
  width: 100%;
}

.aggregation-detail-heading {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.aggregation-detail-hint {
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.aggregation-detail-selection {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.aggregation-detail-selected {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}
</style>
