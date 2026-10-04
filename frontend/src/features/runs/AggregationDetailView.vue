<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'

import RunProvenance from './RunProvenance.vue'
import { useAggregation } from './useAggregations'
import { useArtifactRouteContext } from './useArtifactRouteContext'
import { useRunExecutions } from './useRunDetail'
import { useStatusLabel } from './useStatusLabel'

const { t, d } = useI18n()
const label = useStatusLabel()
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

const resolvedConfig = computed(() =>
  JSON.stringify(aggregation.data.value?.resolved_config ?? {}, null, 2),
)
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
          <span :class="`aggregation-detail-status--${aggregation.data.value.status}`">{{
            label(aggregation.data.value.status)
          }}</span>
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
              <code class="aggregation-detail-hash">{{
                aggregation.data.value.config_sha256
              }}</code>
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
          <pre class="aggregation-detail-config">{{ resolvedConfig }}</pre>
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
              <template v-if="entry.execution">
                <span class="aggregation-detail-method">{{ entry.execution.method_name }}</span>
                <span class="aggregation-detail-version">{{
                  entry.execution.implementation_version
                }}</span>
                <span>{{ label(entry.execution.status) }}</span>
              </template>
              <code v-else class="aggregation-detail-hash">{{ entry.id }}</code>
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

.aggregation-detail-status--completed {
  color: var(--good);
}

.aggregation-detail-status--failed {
  color: var(--critical-text);
}

.aggregation-detail-facts {
  inline-size: 100%;
}

.aggregation-detail-hash {
  font-size: var(--font-size-small);
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

.aggregation-detail-config {
  margin: 0;
  padding: var(--space-3);
  overflow-x: auto;
  border-radius: var(--radius-input);
  background: var(--surface-1);
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

.aggregation-detail-method {
  font-weight: var(--weight-semibold);
}

.aggregation-detail-version {
  color: var(--text-secondary);
}
</style>
