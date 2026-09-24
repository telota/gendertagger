<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useProject } from '@/features/projects/useProjects'
import { useRun } from '@/features/runs/useRunDetail'

import EvaluationItem from './EvaluationItem.vue'
import NewEvaluationForm from './NewEvaluationForm.vue'
import { useEvaluationList } from './useEvaluations'

const { t } = useI18n()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')

const project = useProject(projectId, isSignedIn)
// Starting an evaluation is a project-scoped operator action, like a run or an aggregation.
const canRun = computed(() => project.data.value?.current_user_role === 'operator')

const run = useRun(runId, isSignedIn)
const list = useEvaluationList(runId, isSignedIn)
const items = computed(() => list.data.value?.pages.flatMap((page) => page.items) ?? [])
</script>

<template>
  <main class="evaluation-list-view">
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('runs.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="evaluation-list-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('runs.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <RouterLink
        v-if="run.data.value"
        class="evaluation-list-back"
        :to="{
          name: 'runDetail',
          params: { projectId, snapshotId: run.data.value.dataset_snapshot_id, runId },
        }"
      >
        {{ t('evaluation.backToRun') }}
      </RouterLink>
      <h1 class="evaluation-list-title">{{ t('evaluation.title') }}</h1>
      <p class="evaluation-list-intro">{{ t('evaluation.intro') }}</p>

      <NewEvaluationForm
        v-if="canRun"
        class="evaluation-list-new"
        :project-id="projectId"
        :run-id="runId"
        :earlier="items"
      />
      <p v-else-if="project.data.value" class="evaluation-list-forbidden">
        {{ t('evaluation.forbidden') }}
      </p>

      <section class="evaluation-list" aria-labelledby="evaluation-list-heading">
        <h2 id="evaluation-list-heading" class="evaluation-list-heading">
          {{ t('evaluation.history') }}
        </h2>
        <p v-if="list.isPending.value" role="status">{{ t('runs.loading') }}</p>
        <div v-else-if="list.isError.value" class="evaluation-list-load-error">
          <p role="alert">{{ t('evaluation.loadError') }}</p>
          <AppButton class="evaluation-list-retry" type="button" @click="() => list.refetch()">
            {{ t('runs.retry') }}
          </AppButton>
        </div>
        <template v-else>
          <p v-if="items.length === 0" class="evaluation-list-empty">{{ t('evaluation.empty') }}</p>
          <ul v-else class="evaluation-list-items">
            <EvaluationItem
              v-for="evaluation in items"
              :key="evaluation.id"
              :evaluation="evaluation"
              :project-id="projectId"
            />
          </ul>
          <AppButton
            v-if="list.hasNextPage.value"
            class="evaluation-list-more"
            type="button"
            @click="() => list.fetchNextPage()"
          >
            {{ t('runs.loadMore') }}
          </AppButton>
        </template>
      </section>
    </template>
  </main>
</template>

<style scoped>
.evaluation-list-view {
  padding: var(--space-8) var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.evaluation-list-title {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
}

.evaluation-list-back {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.evaluation-list-intro,
.evaluation-list-forbidden,
.evaluation-list-empty {
  margin: 0;
  max-width: 48rem;
  color: var(--text-secondary);
}

.evaluation-list-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.evaluation-list-load-error p {
  margin: 0;
  color: var(--critical);
}

.evaluation-list-new,
.evaluation-list {
  width: 100%;
  max-width: 48rem;
}

.evaluation-list-heading {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.evaluation-list-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0 0 var(--space-4);
  padding: 0;
  list-style: none;
}
</style>
