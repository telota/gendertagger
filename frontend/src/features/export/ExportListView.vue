<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useProject } from '@/features/projects/useProjects'
import { useRun } from '@/features/runs/useRunDetail'

import ExportItem from './ExportItem.vue'
import NewExportForm from './NewExportForm.vue'
import { useExportList } from './useExports'

const { t } = useI18n()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')

const project = useProject(projectId, isSignedIn)
// Starting an export is a project-scoped operator action, like a run, an aggregation or an evaluation.
const canRun = computed(() => project.data.value?.current_user_role === 'operator')

const run = useRun(runId, isSignedIn)
const list = useExportList(runId, isSignedIn)
const items = computed(() => list.data.value?.pages.flatMap((page) => page.items) ?? [])
</script>

<template>
  <main class="export-list-view">
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('runs.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="export-list-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('runs.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <RouterLink
        v-if="run.data.value"
        class="export-list-back"
        :to="{
          name: 'runDetail',
          params: { projectId, snapshotId: run.data.value.dataset_snapshot_id, runId },
        }"
      >
        {{ t('export.backToRun') }}
      </RouterLink>
      <h1 class="export-list-title">{{ t('export.title') }}</h1>
      <p class="export-list-intro">{{ t('export.intro') }}</p>

      <NewExportForm
        v-if="canRun"
        class="export-list-new"
        :project-id="projectId"
        :run-id="runId"
      />
      <p v-else-if="project.data.value" class="export-list-forbidden">
        {{ t('export.forbidden') }}
      </p>

      <section class="export-list" aria-labelledby="export-list-heading">
        <h2 id="export-list-heading" class="export-list-heading">{{ t('export.history') }}</h2>
        <p v-if="list.isPending.value" role="status">{{ t('runs.loading') }}</p>
        <div v-else-if="list.isError.value" class="export-list-load-error">
          <p role="alert">{{ t('export.loadError') }}</p>
          <AppButton class="export-list-retry" type="button" @click="() => list.refetch()">
            {{ t('runs.retry') }}
          </AppButton>
        </div>
        <template v-else>
          <p v-if="items.length === 0" class="export-list-empty">{{ t('export.empty') }}</p>
          <ul v-else class="export-list-items">
            <ExportItem v-for="item in items" :key="item.id" :item="item" :project-id="projectId" />
          </ul>
          <AppButton
            v-if="list.hasNextPage.value"
            class="export-list-more"
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
.export-list-view {
  padding: var(--space-8) var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.export-list-title {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
}

.export-list-back {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.export-list-intro,
.export-list-forbidden,
.export-list-empty {
  margin: 0;
  max-width: 48rem;
  color: var(--text-secondary);
}

.export-list-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.export-list-load-error p {
  margin: 0;
  color: var(--critical-text);
}

.export-list-new,
.export-list {
  width: 100%;
  max-width: 48rem;
}

.export-list-heading {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.export-list-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0 0 var(--space-4);
  padding: 0;
  list-style: none;
}
</style>
