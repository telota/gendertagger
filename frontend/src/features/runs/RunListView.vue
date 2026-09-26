<script setup lang="ts">
import { PhMinus, PhPlus } from '@phosphor-icons/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { hasProjectRole } from '@/features/projects/projectRoles'
import { useProject } from '@/features/projects/useProjects'
import { useImportedSnapshot } from '@/features/projects/useSnapshotData'

import NewRunForm from './NewRunForm.vue'
import RunItem from './RunItem.vue'
import { useRunList, type Run } from './useRuns'

const { t, d } = useI18n()
const router = useRouter()
const { session, isSignedIn, retrySession } = useRequireSession()
const projectId = useRouteParam('projectId')
const snapshotId = useRouteParam('snapshotId')
const project = useProject(projectId, isSignedIn)
const snapshot = useImportedSnapshot(projectId, snapshotId, isSignedIn)
const canRead = computed(
  () =>
    isSignedIn.value &&
    project.isSuccess.value &&
    project.data.value?.id === projectId.value &&
    hasProjectRole(project.data.value.current_user_role, 'viewer') &&
    snapshot.data.value?.id === snapshotId.value &&
    snapshot.data.value.project_id === projectId.value &&
    snapshot.data.value.status === 'ready',
)
const canRun = computed(
  () => canRead.value && hasProjectRole(project.data.value?.current_user_role, 'operator'),
)
const runs = useRunList(snapshotId, canRead)
const items = computed(() => runs.data.value?.pages.flatMap((page) => page.items) ?? [])
const formOpen = ref(false)
const formMounted = ref(false)
const form = ref<InstanceType<typeof NewRunForm>>()

async function toggleForm(): Promise<void> {
  formOpen.value = !formOpen.value
  if (!formOpen.value) return
  formMounted.value = true
  await nextTick()
  form.value?.focusHeading()
}

function resetForm(): void {
  formOpen.value = false
  formMounted.value = false
}
watch([() => session.user?.id, projectId, snapshotId], resetForm)
watch(canRun, (allowed) => {
  if (!allowed) resetForm()
})

// A started run is watched live, so the operator lands on it rather than back on the list.
function openRun(run: Run): void {
  void router.push({
    name: 'runDetail',
    params: { projectId: projectId.value, snapshotId: snapshotId.value, runId: run.id },
  })
}

function retryContext(): void {
  if (project.isFetching.value || snapshot.isFetching.value) return
  void project.refetch()
  void snapshot.refetch()
}

function retryRuns(): void {
  if (!runs.isFetching.value) void runs.refetch()
}

function loadMore(): void {
  if (!runs.isFetching.value) void runs.fetchNextPage()
}
</script>

<template>
  <main class="run-list-view app-page-frame">
    <header class="run-list-heading-row app-page-heading">
      <h1 class="run-list-title app-page-heading__title">{{ t('runs.title') }}</h1>
      <div v-if="canRun" class="app-page-heading__actions">
        <AppButton
          class="run-list-create"
          :variant="formOpen ? 'ghost' : 'solid'"
          :aria-expanded="formOpen"
          aria-controls="new-classification-panel"
          @click="toggleForm"
        >
          <PhMinus v-if="formOpen" :size="18" aria-hidden="true" />
          <PhPlus v-else :size="18" aria-hidden="true" />
          {{ formOpen ? t('runs.new.hide') : t('runs.new.show') }}
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
      class="run-list-load-error app-card"
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
        class="run-list-load-error app-card"
        announcement="assertive"
        tone="critical"
      >
        {{ t('runs.contextLoadError') }}
        <template #actions>
          <AppButton
            variant="ghost"
            :disabled="project.isFetching.value || snapshot.isFetching.value"
            @click="retryContext"
          >
            {{ t('runs.retry') }}
          </AppButton>
        </template>
      </AppFeedback>
      <AppFeedback
        v-else-if="project.isPending.value || snapshot.isPending.value"
        class="app-card"
        announcement="polite"
      >
        {{ t('runs.loading') }}
      </AppFeedback>
      <div v-else-if="!canRead" class="run-list-unavailable app-card">
        <p>{{ t('runs.contextUnavailable') }}</p>
        <RouterLink :to="{ name: 'projectClassification', params: { projectId } }">
          {{ t('runs.changeSelection') }}
        </RouterLink>
      </div>
      <template v-else>
        <div class="run-list-context app-card">
          <span v-if="snapshot.data.value">
            {{
              t('data.snapshotTitle', {
                date: d(new Date(snapshot.data.value.created_at), 'timestamp'),
              })
            }}
          </span>
          <RouterLink :to="{ name: 'projectClassification', params: { projectId } }">
            {{ t('runs.changeSelection') }}
          </RouterLink>
        </div>
        <div
          v-show="formOpen && canRun"
          id="new-classification-panel"
          class="run-list-new app-card"
        >
          <NewRunForm
            v-if="formMounted && canRun"
            ref="form"
            :snapshot-id="snapshotId"
            @created="openRun"
          />
        </div>
        <section class="run-list" aria-labelledby="run-list-heading">
          <h2 id="run-list-heading" class="run-list-heading">{{ t('runs.history') }}</h2>
          <AppFeedback v-if="runs.isPending.value" class="app-card" announcement="polite">
            {{ t('runs.loading') }}
          </AppFeedback>
          <AppFeedback
            v-else-if="runs.isError.value && !runs.data.value"
            class="run-list-load-error app-card"
            announcement="assertive"
            tone="critical"
          >
            {{ t('runs.loadError') }}
            <template #actions>
              <AppButton
                class="run-list-retry"
                variant="ghost"
                :disabled="runs.isFetching.value"
                @click="retryRuns"
              >
                {{ t('runs.retry') }}
              </AppButton>
            </template>
          </AppFeedback>
          <template v-else>
            <p v-if="items.length === 0" class="run-list-empty app-card">
              {{ t('runs.empty') }}
            </p>
            <ul v-else class="run-list-items" :aria-busy="runs.isFetching.value || undefined">
              <RunItem v-for="run in items" :key="run.id" :run="run" :project-id="projectId" />
            </ul>
            <AppFeedback
              v-if="runs.isError.value"
              class="run-list-feedback app-card"
              announcement="assertive"
              tone="critical"
            >
              {{ t('runs.loadError') }}
              <template v-if="!runs.isFetchNextPageError.value" #actions>
                <AppButton
                  class="run-list-retry"
                  variant="ghost"
                  :disabled="runs.isFetching.value"
                  @click="retryRuns"
                >
                  {{ t('runs.retry') }}
                </AppButton>
              </template>
            </AppFeedback>
            <AppFeedback
              v-if="runs.isFetchingNextPage.value"
              class="run-list-feedback app-card"
              announcement="polite"
            >
              {{ t('runs.loading') }}
            </AppFeedback>
            <AppButton
              v-if="runs.hasNextPage.value"
              class="run-list-load-more"
              variant="ghost"
              :disabled="runs.isFetching.value"
              @click="loadMore"
            >
              {{ runs.isFetchNextPageError.value ? t('runs.retry') : t('runs.loadMore') }}
            </AppButton>
          </template>
        </section>
      </template>
    </template>
  </main>
</template>

<style scoped>
.run-list-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}
.run-list-context {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3) var(--space-6);
}
.run-list-heading-row {
  inline-size: 100%;
  margin-block-end: 0;
}
.run-list-create svg {
  flex-shrink: 0;
}
.run-list-context,
.run-list-unavailable,
.run-list-empty {
  color: var(--text-secondary);
}
.run-list-context a,
.run-list-unavailable a {
  color: var(--accent);
  text-underline-offset: 0.2em;
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
.run-list-feedback {
  margin-block-end: var(--space-4);
}
</style>
