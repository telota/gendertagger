<script setup lang="ts">
import { PhMinus, PhPlus } from '@phosphor-icons/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useProject } from '@/composables/useProjects'
import { useRun } from '@/composables/useRunDetail'

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
const formOpen = ref(false)
const formMounted = ref(false)
const form = ref<InstanceType<typeof NewEvaluationForm>>()

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
  <main class="evaluation-list-view app-page-frame">
    <RouterLink
      v-if="isSignedIn && run.data.value"
      class="evaluation-list-back"
      :to="{
        name: 'runDetail',
        params: { projectId, snapshotId: run.data.value.dataset_snapshot_id, runId },
      }"
    >
      {{ t('evaluation.backToRun') }}
    </RouterLink>
    <header class="evaluation-list-page-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="evaluation-list-title app-page-heading__title">
          {{ t('evaluation.title') }}
        </h1>
        <p class="evaluation-list-intro app-page-heading__description">
          {{ t('evaluation.intro') }}
        </p>
      </div>
      <div v-if="canRun" class="app-page-heading__actions">
        <AppButton
          class="evaluation-list-create"
          :variant="formOpen ? 'ghost' : 'solid'"
          :aria-expanded="formOpen"
          aria-controls="new-evaluation-panel"
          @click="toggleForm"
        >
          <PhMinus v-if="formOpen" :size="18" aria-hidden="true" />
          <PhPlus v-else :size="18" aria-hidden="true" />
          {{ formOpen ? t('evaluation.new.hide') : t('evaluation.new.show') }}
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
      class="evaluation-list-load-error app-card"
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
      <div
        v-if="canRun"
        v-show="formOpen"
        id="new-evaluation-panel"
        class="evaluation-list-new app-card"
      >
        <NewEvaluationForm
          v-if="formMounted"
          ref="form"
          :project-id="projectId"
          :run-id="runId"
          :earlier="items"
        />
      </div>
      <p v-else-if="project.data.value" class="evaluation-list-forbidden app-card">
        {{ t('evaluation.forbidden') }}
      </p>

      <section class="evaluation-list" aria-labelledby="evaluation-list-heading">
        <h2 id="evaluation-list-heading" class="evaluation-list-heading">
          {{ t('evaluation.history') }}
        </h2>
        <AppFeedback
          v-if="list.isPending.value"
          class="evaluation-list-state app-card"
          announcement="polite"
        >
          {{ t('runs.loading') }}
        </AppFeedback>
        <AppFeedback
          v-else-if="list.isError.value && !list.data.value"
          class="evaluation-list-load-error app-card"
          announcement="assertive"
          tone="critical"
        >
          {{ t('evaluation.loadError') }}
          <template #actions>
            <AppButton
              class="evaluation-list-retry"
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
          <p v-if="items.length === 0" class="evaluation-list-empty app-card">
            {{ t('evaluation.empty') }}
          </p>
          <ul v-else class="evaluation-list-items" :aria-busy="list.isFetching.value || undefined">
            <EvaluationItem
              v-for="evaluation in items"
              :key="evaluation.id"
              :evaluation="evaluation"
              :project-id="projectId"
            />
          </ul>
          <AppFeedback
            v-if="list.isError.value"
            class="evaluation-list-feedback app-card"
            announcement="assertive"
            tone="critical"
          >
            {{ t('evaluation.loadError') }}
            <template v-if="!list.isFetchNextPageError.value" #actions>
              <AppButton
                class="evaluation-list-retry"
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
            class="evaluation-list-feedback app-card"
            announcement="polite"
          >
            {{ t('runs.loading') }}
          </AppFeedback>
          <AppButton
            v-if="list.hasNextPage.value"
            class="evaluation-list-more"
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
.evaluation-list-view {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
}

.evaluation-list-page-heading {
  width: 100%;
  margin-block-end: var(--space-2);
}

.evaluation-list-back {
  align-self: flex-start;
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.evaluation-list-forbidden,
.evaluation-list-empty {
  margin: 0;
  color: var(--text-secondary);
}

.evaluation-list-new,
.evaluation-list,
.evaluation-list-forbidden {
  width: 100%;
}

.evaluation-list-create svg {
  flex-shrink: 0;
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

.evaluation-list-feedback {
  margin-block-end: var(--space-4);
}
</style>
