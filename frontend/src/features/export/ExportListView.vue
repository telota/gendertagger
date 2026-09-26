<script setup lang="ts">
import { PhMinus, PhPlus } from '@phosphor-icons/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
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
const canRun = computed(
  () =>
    isSignedIn.value &&
    project.data.value?.id === projectId.value &&
    project.data.value.current_user_role === 'operator',
)

const run = useRun(runId, isSignedIn)
const list = useExportList(runId, isSignedIn)
const items = computed(() => list.data.value?.pages.flatMap((page) => page.items) ?? [])
const formOpen = ref(false)
const formMounted = ref(false)
const form = ref<InstanceType<typeof NewExportForm>>()

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

watch([() => session.user?.id, projectId, runId], resetForm)
watch(canRun, (allowed) => {
  if (!allowed) resetForm()
})

function retryList(): void {
  if (!list.isFetching.value) void list.refetch()
}

function loadMore(): void {
  if (!list.isFetching.value) void list.fetchNextPage()
}
</script>

<template>
  <main class="export-list-view app-page-frame">
    <RouterLink
      v-if="isSignedIn && run.data.value"
      class="export-list-back"
      :to="{
        name: 'runDetail',
        params: { projectId, snapshotId: run.data.value.dataset_snapshot_id, runId },
      }"
    >
      {{ t('export.backToRun') }}
    </RouterLink>
    <header class="export-list-page-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="export-list-title app-page-heading__title">{{ t('export.title') }}</h1>
        <p class="export-list-intro app-page-heading__description">{{ t('export.intro') }}</p>
      </div>
      <div v-if="canRun" class="app-page-heading__actions">
        <AppButton
          class="export-list-create"
          :variant="formOpen ? 'ghost' : 'solid'"
          :aria-expanded="formOpen"
          aria-controls="new-export-panel"
          @click="toggleForm"
        >
          <PhMinus v-if="formOpen" :size="18" aria-hidden="true" />
          <PhPlus v-else :size="18" aria-hidden="true" />
          {{ formOpen ? t('export.new.hide') : t('export.new.show') }}
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
      class="export-list-load-error app-card"
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
      <div v-show="formOpen && canRun" id="new-export-panel" class="export-list-new app-card">
        <NewExportForm
          v-if="formMounted && canRun"
          ref="form"
          :project-id="projectId"
          :run-id="runId"
        />
      </div>
      <p v-if="project.data.value && !canRun" class="export-list-forbidden app-card">
        {{ t('export.forbidden') }}
      </p>

      <section class="export-list" aria-labelledby="export-list-heading">
        <h2 id="export-list-heading" class="export-list-heading">{{ t('export.history') }}</h2>
        <AppFeedback
          v-if="list.isPending.value"
          class="export-list-state app-card"
          announcement="polite"
        >
          {{ t('runs.loading') }}
        </AppFeedback>
        <AppFeedback
          v-else-if="list.isError.value && !list.data.value"
          class="export-list-load-error app-card"
          announcement="assertive"
          tone="critical"
        >
          {{ t('export.loadError') }}
          <template #actions>
            <AppButton
              class="export-list-retry"
              type="button"
              variant="ghost"
              :disabled="list.isFetching.value"
              @click="retryList"
            >
              {{ t('runs.retry') }}
            </AppButton>
          </template>
        </AppFeedback>
        <template v-else>
          <p v-if="items.length === 0" class="export-list-empty app-card">
            {{ t('export.empty') }}
          </p>
          <ul v-else class="export-list-items" :aria-busy="list.isFetching.value || undefined">
            <ExportItem v-for="item in items" :key="item.id" :item="item" :project-id="projectId" />
          </ul>
          <AppFeedback
            v-if="list.isError.value"
            class="export-list-feedback app-card"
            announcement="assertive"
            tone="critical"
          >
            {{ t('export.loadError') }}
            <template v-if="!list.isFetchNextPageError.value" #actions>
              <AppButton
                class="export-list-retry"
                type="button"
                variant="ghost"
                :disabled="list.isFetching.value"
                @click="retryList"
              >
                {{ t('runs.retry') }}
              </AppButton>
            </template>
          </AppFeedback>
          <AppFeedback
            v-if="list.isFetchingNextPage.value"
            class="export-list-feedback app-card"
            announcement="polite"
          >
            {{ t('runs.loading') }}
          </AppFeedback>
          <AppButton
            v-if="list.hasNextPage.value"
            class="export-list-more"
            type="button"
            variant="ghost"
            :disabled="list.isFetching.value"
            @click="loadMore"
          >
            {{ list.isFetchNextPageError.value ? t('runs.retry') : t('runs.loadMore') }}
          </AppButton>
        </template>
      </section>
    </template>
  </main>
</template>

<style scoped>
.export-list-view {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
}

.export-list-page-heading {
  width: 100%;
  margin-block-end: var(--space-2);
}

.export-list-create svg {
  flex-shrink: 0;
}

.export-list-back {
  align-self: flex-start;
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.export-list-forbidden,
.export-list-empty {
  margin: 0;
  color: var(--text-secondary);
}

.export-list-new,
.export-list,
.export-list-forbidden {
  width: 100%;
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

.export-list-feedback {
  margin-block-end: var(--space-4);
}
</style>
