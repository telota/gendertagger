<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useProject } from '@/features/projects/useProjects'

import NewRunForm from './NewRunForm.vue'
import RunItem from './RunItem.vue'
import { useRunList, type Run } from './useRuns'

const { t } = useI18n()
const router = useRouter()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const snapshotId = useRouteParam('snapshotId')

const project = useProject(projectId, isSignedIn)
// Starting a run is a project-scoped operator action, like importing a snapshot.
const canRun = computed(() => project.data.value?.current_user_role === 'operator')

const runs = useRunList(snapshotId, isSignedIn)
const items = computed(() => runs.data.value?.pages.flatMap((page) => page.items) ?? [])

// A started run is watched live, so the operator lands on it rather than back on the list.
function openRun(run: Run): void {
  void router.push({
    name: 'runDetail',
    params: { projectId: projectId.value, snapshotId: snapshotId.value, runId: run.id },
  })
}

function loadMore(): void {
  void runs.fetchNextPage()
}
</script>

<template>
  <main class="run-list-view">
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('runs.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="run-list-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('runs.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <h1 class="run-list-title">{{ t('runs.title') }}</h1>
      <RouterLink class="run-list-back" :to="{ name: 'projectOverview', params: { projectId } }">
        {{ t('runs.backToOverview') }}
      </RouterLink>

      <NewRunForm v-if="canRun" class="run-list-new" :snapshot-id="snapshotId" @created="openRun" />
      <p v-else-if="project.data.value" class="run-list-forbidden">{{ t('runs.forbidden') }}</p>

      <section class="run-list" aria-labelledby="run-list-heading">
        <h2 id="run-list-heading" class="run-list-heading">{{ t('runs.history') }}</h2>
        <p v-if="runs.isPending.value" role="status">{{ t('runs.loading') }}</p>
        <div v-else-if="runs.isError.value" class="run-list-load-error">
          <p role="alert">{{ t('runs.loadError') }}</p>
          <AppButton class="run-list-retry" type="button" @click="() => runs.refetch()">
            {{ t('runs.retry') }}
          </AppButton>
        </div>
        <template v-else>
          <p v-if="items.length === 0" class="run-list-empty">{{ t('runs.empty') }}</p>
          <ul v-else class="run-list-items">
            <RunItem v-for="run in items" :key="run.id" :run="run" :project-id="projectId" />
          </ul>
          <AppButton
            v-if="runs.hasNextPage.value"
            class="run-list-load-more"
            type="button"
            @click="loadMore"
          >
            {{ t('runs.loadMore') }}
          </AppButton>
        </template>
      </section>
    </template>
  </main>
</template>

<style scoped>
.run-list-view {
  padding: var(--space-8) var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.run-list-title {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
}

.run-list-back {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.run-list-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.run-list-load-error p {
  margin: 0;
  color: var(--critical-text);
}

.run-list-forbidden,
.run-list-empty {
  color: var(--text-secondary);
}

.run-list-new,
.run-list {
  width: 100%;
  max-width: 48rem;
}

.run-list-heading {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.run-list-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0 0 var(--space-4);
  padding: 0;
  list-style: none;
}
</style>
