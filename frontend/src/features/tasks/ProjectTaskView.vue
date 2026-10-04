<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useProjectIdentity } from '@/composables/useProjectIdentity'
import { useRequireSession } from '@/composables/useRequireSession'
import { hasProjectRole } from '@/composables/projectRoles'
import { useImportedSnapshot } from '@/composables/useSnapshotData'
import { useStatusLabel } from '@/composables/useStatusLabel'

import {
  useTaskSnapshots,
  useTaskRuns,
  useTaskResults,
  useTaskRun,
  useProjectReviewResults,
  useWorkingSelection,
  type Snapshot,
  type TaskMode,
} from './useTaskData'

const props = defineProps<{ mode: TaskMode }>()
const { t, d, n } = useI18n()
const route = useRoute()
const router = useRouter()
const statusLabel = useStatusLabel()
const { session, isSignedIn, retrySession } = useRequireSession()
const { projectId, project, query: projectQuery } = useProjectIdentity()
const gameDisabled = computed(
  () => props.mode === 'game' && project.value !== null && project.value.game_mode_enabled !== true,
)
const canEnter = computed(
  () =>
    project.value !== null &&
    !gameDisabled.value &&
    (props.mode === 'classification' ||
      hasProjectRole(project.value.current_user_role, 'reviewer')),
)
const title = computed(() => {
  if (props.mode === 'classification') return t('runs.title')
  if (props.mode === 'review') return t('review.title')
  if (props.mode === 'game') return t('game.title')
  // The merged Redigieren entry (D25): it resolves to the workbench or to plain annotation per
  // dataset, so its own heading names the tab, not either destination.
  return t('nav.review')
})
const description = computed(() => {
  if (props.mode === 'classification') return t('taskEntry.classificationHint')
  if (props.mode === 'review') return t('taskEntry.reviewHint')
  if (props.mode === 'game') return t('taskEntry.gameHint')
  return t('taskEntry.annotationHint')
})
const selectedSnapshotId = computed(() =>
  props.mode !== 'classification' &&
  props.mode !== 'game' &&
  typeof route.query.snapshot === 'string'
    ? route.query.snapshot
    : '',
)
const selectedRunId = computed(() => (typeof route.query.run === 'string' ? route.query.run : ''))
const snapshotQuery = useImportedSnapshot(
  projectId,
  selectedSnapshotId,
  computed(() => canEnter.value && selectedSnapshotId.value !== ''),
)
const snapshot = computed(() => {
  const value = snapshotQuery.data.value
  return snapshotQuery.isSuccess.value &&
    value?.id === selectedSnapshotId.value &&
    value.project_id === projectId.value &&
    value.status === 'ready'
    ? value
    : null
})
const snapshotsQuery = useTaskSnapshots(
  projectId,
  computed(() => props.mode === 'review' || props.mode === 'game'),
  computed(
    () =>
      canEnter.value &&
      props.mode !== 'review' &&
      props.mode !== 'game' &&
      !selectedSnapshotId.value,
  ),
)
const snapshots = computed(
  () =>
    snapshotsQuery.data.value?.pages
      .flatMap((page) => page.items)
      .filter((item) => item.project_id === projectId.value && item.status === 'ready') ?? [],
)
const chooseEvidence = computed(
  () => props.mode === 'review' || route.query.evidence === '1' || selectedRunId.value !== '',
)
const runsQuery = useTaskRuns(
  selectedSnapshotId,
  computed(() => snapshot.value !== null && chooseEvidence.value && !selectedRunId.value),
)
const runs = computed(
  () =>
    runsQuery.data.value?.pages
      .flatMap((page) => page.items)
      .filter((item) => item.dataset_snapshot_id === selectedSnapshotId.value) ?? [],
)
const runQuery = useTaskRun(
  projectId,
  selectedSnapshotId,
  selectedRunId,
  computed(() => snapshot.value !== null && selectedRunId.value !== ''),
)
const run = computed(() =>
  runQuery.isSuccess.value &&
  runQuery.data.value?.id === selectedRunId.value &&
  runQuery.data.value.dataset_snapshot_id === selectedSnapshotId.value
    ? runQuery.data.value
    : null,
)
const resultsQuery = useTaskResults(
  selectedRunId,
  computed(() => run.value !== null),
)
const results = computed(
  () =>
    resultsQuery.data.value?.pages
      .flatMap((page) => page.items)
      .filter((item) => item.run_id === selectedRunId.value && item.status === 'completed') ?? [],
)
const reviewResultsQuery = useProjectReviewResults(
  projectId,
  computed(
    () =>
      canEnter.value &&
      (props.mode === 'review' || props.mode === 'game') &&
      !selectedSnapshotId.value,
  ),
)
const reviewResults = computed(
  () =>
    reviewResultsQuery.data.value?.pages
      .flatMap((page) => page.items)
      .filter((item) => item.snapshot.project_id === projectId.value) ?? [],
)
const workingId = computed(() => project.value?.working_aggregation_execution_id ?? null)
const workingQuery = useWorkingSelection(projectId, workingId, canEnter)
const working = computed(() =>
  workingQuery.isSuccess.value && workingQuery.data.value?.aggregationId === workingId.value
    ? workingQuery.data.value
    : null,
)
/**
 * Redigieren's fast path (D25): whatever is relevant right now, one click away, before the reviewer
 * has to pick anything. A completed classification (the project's explicit working aggregation, ADR-0035)
 * opens the workbench directly; otherwise the newest ready dataset opens direct manual annotation. Never
 * a silent choice among several completed aggregations — that stays an explicit pick in the list below.
 */
type CurrentDatasetAction =
  | { kind: 'loading' }
  | { kind: 'review'; runId: string; aggregationId: string }
  | { kind: 'annotate'; snapshot: Snapshot }
const currentDatasetAction = computed<CurrentDatasetAction | null>(() => {
  if (props.mode !== 'annotation') return null
  if (workingId.value && workingQuery.isPending.value) return { kind: 'loading' }
  if (working.value) {
    return {
      kind: 'review',
      runId: working.value.runId,
      aggregationId: working.value.aggregationId,
    }
  }
  if (snapshotsQuery.isPending.value) return { kind: 'loading' }
  const newest = snapshots.value[0]
  return newest ? { kind: 'annotate', snapshot: newest } : null
})
const stepHeading = ref<HTMLElement | null>(null)
const annotationHeading = ref<HTMLElement | null>(null)
const activeHeading = computed(() =>
  props.mode === 'annotation' && snapshot.value && !chooseEvidence.value
    ? annotationHeading.value
    : stepHeading.value,
)
const awaitingStepFocus = ref(false)

function focusStep(): void {
  if (!awaitingStepFocus.value || !activeHeading.value) return
  activeHeading.value.focus()
  awaitingStepFocus.value = false
}

function selectSnapshot(id: string): void {
  if (props.mode === 'classification') {
    void router.push({
      name: 'snapshotRuns',
      params: { projectId: projectId.value, snapshotId: id },
    })
  } else {
    void router.push({ query: { snapshot: id } })
  }
}

watch([selectedSnapshotId, selectedRunId, chooseEvidence], async () => {
  awaitingStepFocus.value = true
  await nextTick()
  focusStep()
})
// A selected snapshot may need an asynchronous read before its next step exists in the DOM.
// Focus once for that transition; background refreshes must not move the user's focus again.
watch(activeHeading, focusStep, { flush: 'post' })
</script>

<template>
  <main class="task-entry app-page-frame">
    <header class="task-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="app-page-heading__title">{{ title }}</h1>
        <p class="app-page-heading__description">{{ description }}</p>
      </div>
    </header>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      announcement="polite"
      >{{ t('review.loading') }}</AppFeedback
    >
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="app-card"
      tone="critical"
      announcement="assertive"
    >
      {{ t('projects.sessionLoadError') }}
      <template #actions
        ><AppButton variant="ghost" @click="retrySession">{{
          t('projects.retry')
        }}</AppButton></template
      >
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <AppFeedback v-if="projectQuery.isPending.value" class="app-card" announcement="polite">
        {{ t('projects.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="projectQuery.isError.value"
        class="app-card"
        tone="critical"
        announcement="assertive"
      >
        {{ t('data.projectLoadError') }}
        <template #actions
          ><AppButton variant="ghost" @click="projectQuery.refetch()">{{
            t('projects.retry')
          }}</AppButton></template
        >
      </AppFeedback>
      <AppFeedback v-else-if="gameDisabled" class="app-card">{{ t('game.disabled') }}</AppFeedback>
      <AppFeedback v-else-if="!canEnter" class="app-card">{{
        t('taskEntry.noPermission')
      }}</AppFeedback>
      <template v-else>
        <AppFeedback
          v-if="workingId && workingQuery.isError.value"
          class="app-card"
          tone="critical"
          announcement="polite"
        >
          {{ t('taskEntry.recommendationError') }}
          <template #actions
            ><AppButton variant="ghost" @click="workingQuery.refetch()">{{
              t('projects.retry')
            }}</AppButton></template
          >
        </AppFeedback>
        <section
          v-if="(mode === 'review' || mode === 'game') && !selectedSnapshotId"
          aria-labelledby="task-review-results-title"
        >
          <h2 id="task-review-results-title" ref="stepHeading" tabindex="-1">
            {{ mode === 'game' ? t('game.selectResult') : t('taskEntry.reviewResultsTitle') }}
          </h2>
          <AppFeedback
            v-if="reviewResultsQuery.isPending.value"
            class="app-card"
            announcement="polite"
          >
            {{ t('review.loading') }}
          </AppFeedback>
          <AppFeedback
            v-if="reviewResultsQuery.isError.value"
            class="app-card"
            tone="critical"
            announcement="assertive"
          >
            {{ t('taskEntry.resultError') }}
            <template #actions
              ><AppButton variant="ghost" @click="reviewResultsQuery.refetch()">{{
                t('projects.retry')
              }}</AppButton></template
            >
          </AppFeedback>
          <AppFeedback
            v-else-if="reviewResultsQuery.isSuccess.value && !reviewResults.length"
            class="app-card"
          >
            {{ t('taskEntry.noReviewSnapshots') }}
            <template #actions
              ><AppButton
                variant="ghost"
                :to="{ name: 'projectClassification', params: { projectId } }"
                >{{ t('nav.classification') }}</AppButton
              ></template
            >
          </AppFeedback>
          <ul class="task-options task-options--cards">
            <li
              v-for="entry in reviewResults"
              :key="entry.aggregation.id"
              class="task-option app-resource-card"
            >
              <div>
                <h3>
                  {{
                    t('taskEntry.resultTitle', {
                      date: d(new Date(entry.aggregation.created_at), 'timestamp'),
                    })
                  }}
                </h3>
                <dl class="task-option-facts">
                  <div>
                    <dt>{{ t('taskEntry.dataset') }}</dt>
                    <dd>
                      {{
                        t('data.snapshotTitle', {
                          date: d(new Date(entry.snapshot.created_at), 'timestamp'),
                        })
                      }}
                    </dd>
                  </div>
                  <div>
                    <dt>{{ t('taskEntry.run') }}</dt>
                    <dd>
                      {{
                        t('taskEntry.runTitle', {
                          date: d(new Date(entry.run.created_at), 'timestamp'),
                        })
                      }}
                    </dd>
                  </div>
                  <div>
                    <dt>{{ t('taskEntry.methods') }}</dt>
                    <dd>
                      {{
                        t('taskEntry.methodCount', {
                          count: n(entry.aggregation.method_execution_ids.length, 'integer'),
                        })
                      }}
                    </dd>
                  </div>
                  <div>
                    <dt>{{ t('taskEntry.strategy') }}</dt>
                    <dd>{{ entry.aggregation.strategy }}</dd>
                  </div>
                </dl>
                <span
                  v-if="working?.aggregationId === entry.aggregation.id"
                  class="task-recommended"
                  >{{ t('taskEntry.recommended') }}</span
                >
              </div>
              <AppButton
                variant="ghost"
                :to="{
                  name: mode === 'game' ? 'game' : 'review',
                  params: { projectId, runId: entry.run.id, aggregationId: entry.aggregation.id },
                }"
                :aria-label="
                  t('taskEntry.openResultNamed', {
                    date: d(new Date(entry.aggregation.created_at), 'timestamp'),
                  })
                "
                >{{
                  mode === 'game' ? t('taskEntry.openGame') : t('taskEntry.openReview')
                }}</AppButton
              >
            </li>
          </ul>
          <AppButton
            v-if="reviewResultsQuery.hasNextPage.value"
            variant="ghost"
            :disabled="reviewResultsQuery.isFetchingNextPage.value"
            @click="reviewResultsQuery.fetchNextPage()"
            >{{ t('taskEntry.moreResults') }}</AppButton
          >
        </section>
        <template v-else-if="!selectedSnapshotId">
          <section
            v-if="mode === 'annotation' && currentDatasetAction"
            class="task-current"
            aria-labelledby="task-current-title"
          >
            <h2 id="task-current-title">{{ t('taskEntry.currentDataset') }}</h2>
            <AppFeedback
              v-if="currentDatasetAction.kind === 'loading'"
              class="app-card"
              announcement="polite"
            >
              {{ t('review.loading') }}
            </AppFeedback>
            <ul v-else class="task-options">
              <li class="task-option app-resource-card">
                <div v-if="currentDatasetAction.kind === 'review'">
                  <h3>{{ t('taskEntry.currentClassifiedHint') }}</h3>
                </div>
                <div v-else>
                  <h3>
                    {{
                      t('data.snapshotTitle', {
                        date: d(new Date(currentDatasetAction.snapshot.created_at), 'timestamp'),
                      })
                    }}
                  </h3>
                  <p>
                    {{
                      t('taskEntry.recordCount', {
                        count: n(currentDatasetAction.snapshot.record_count ?? 0, 'integer'),
                      })
                    }}
                  </p>
                </div>
                <AppButton
                  v-if="currentDatasetAction.kind === 'review'"
                  :to="{
                    name: 'review',
                    params: {
                      projectId,
                      runId: currentDatasetAction.runId,
                      aggregationId: currentDatasetAction.aggregationId,
                    },
                  }"
                  >{{ t('taskEntry.openReview') }}</AppButton
                >
                <AppButton
                  v-else
                  :to="{
                    name: 'snapshotAnnotations',
                    params: { projectId, snapshotId: currentDatasetAction.snapshot.id },
                  }"
                  >{{ t('taskEntry.openAnnotation') }}</AppButton
                >
              </li>
            </ul>
          </section>
          <section aria-labelledby="task-snapshots-title">
            <h2 id="task-snapshots-title" ref="stepHeading" tabindex="-1">
              {{
                mode === 'annotation' && currentDatasetAction
                  ? t('taskEntry.selectOtherSnapshot')
                  : t('taskEntry.selectSnapshot')
              }}
            </h2>
            <AppFeedback
              v-if="snapshotsQuery.isPending.value"
              class="app-card"
              announcement="polite"
            >
              {{ t('data.loading') }}
            </AppFeedback>
            <AppFeedback
              v-if="snapshotsQuery.isError.value"
              class="app-card"
              tone="critical"
              announcement="assertive"
            >
              {{ t('taskEntry.snapshotError') }}
              <template #actions
                ><AppButton variant="ghost" @click="snapshotsQuery.refetch()">{{
                  t('projects.retry')
                }}</AppButton></template
              >
            </AppFeedback>
            <AppFeedback
              v-else-if="snapshotsQuery.isSuccess.value && !snapshots.length"
              class="app-card"
            >
              {{
                mode === 'review' ? t('taskEntry.noReviewSnapshots') : t('taskEntry.noSnapshots')
              }}
              <template #actions
                ><AppButton
                  variant="ghost"
                  :to="{
                    name: mode === 'review' ? 'projectClassification' : 'projectOverview',
                    params: { projectId },
                  }"
                  >{{ mode === 'review' ? t('nav.classification') : t('nav.overview') }}</AppButton
                ></template
              >
            </AppFeedback>
            <ul class="task-options">
              <li v-for="entry in snapshots" :key="entry.id" class="task-option app-resource-card">
                <div>
                  <h3>
                    {{
                      t('data.snapshotTitle', { date: d(new Date(entry.created_at), 'timestamp') })
                    }}
                  </h3>
                  <p>
                    {{ t('taskEntry.recordCount', { count: n(entry.record_count ?? 0, 'integer') })
                    }}<span v-if="entry.import_config?.source_format">
                      {{ String(entry.import_config.source_format).toUpperCase() }}</span
                    >
                  </p>
                  <span v-if="working?.snapshotId === entry.id" class="task-recommended">{{
                    t('taskEntry.recommended')
                  }}</span>
                </div>
                <AppButton
                  variant="ghost"
                  :aria-label="
                    t('taskEntry.selectSnapshotNamed', {
                      date: d(new Date(entry.created_at), 'timestamp'),
                    })
                  "
                  @click="selectSnapshot(entry.id)"
                  >{{
                    mode === 'classification'
                      ? t('taskEntry.openClassification')
                      : t('taskEntry.select')
                  }}</AppButton
                >
              </li>
            </ul>
            <AppButton
              v-if="snapshotsQuery.hasNextPage.value"
              variant="ghost"
              :disabled="snapshotsQuery.isFetchingNextPage.value"
              @click="snapshotsQuery.fetchNextPage()"
              >{{ t('taskEntry.moreSnapshots') }}</AppButton
            >
          </section>
        </template>
        <template v-else>
          <AppFeedback v-if="snapshotQuery.isPending.value" class="app-card" announcement="polite">
            {{ t('data.loading') }}
          </AppFeedback>
          <AppFeedback
            v-else-if="!snapshot"
            class="app-card"
            tone="critical"
            announcement="assertive"
          >
            {{ t('taskEntry.selectionUnavailable') }}
            <template #actions
              ><AppButton variant="ghost" @click="snapshotQuery.refetch()">{{
                t('projects.retry')
              }}</AppButton
              ><AppButton variant="ghost" :to="{ query: {} }">{{
                t('taskEntry.changeSnapshot')
              }}</AppButton></template
            >
          </AppFeedback>
          <template v-else>
            <div class="task-context app-resource-card">
              <p>
                {{
                  t('data.snapshotTitle', { date: d(new Date(snapshot.created_at), 'timestamp') })
                }}
              </p>
              <AppButton variant="text" :to="{ query: {} }">{{
                t('taskEntry.changeSnapshot')
              }}</AppButton>
            </div>
            <div v-if="mode === 'annotation'" class="task-annotation-choice app-card">
              <h2 ref="annotationHeading" tabindex="-1">{{ t('taskEntry.annotationStart') }}</h2>
              <p>{{ t('taskEntry.optionalEvidence') }}</p>
              <div class="task-actions">
                <AppButton
                  :to="{
                    name: 'snapshotAnnotations',
                    params: { projectId, snapshotId: snapshot.id },
                  }"
                  >{{ t('taskEntry.withoutEvidence') }}</AppButton
                >
                <AppButton
                  v-if="!chooseEvidence"
                  variant="ghost"
                  :to="{ query: { snapshot: snapshot.id, evidence: '1' } }"
                  >{{ t('taskEntry.chooseEvidence') }}</AppButton
                >
              </div>
            </div>
            <section v-if="chooseEvidence && !selectedRunId" aria-labelledby="task-runs-title">
              <h2 id="task-runs-title" ref="stepHeading" tabindex="-1">
                {{ t('taskEntry.selectRun') }}
              </h2>
              <AppFeedback v-if="runsQuery.isPending.value" class="app-card" announcement="polite">
                {{ t('review.loading') }}
              </AppFeedback>
              <AppFeedback
                v-if="runsQuery.isError.value"
                class="app-card"
                tone="critical"
                announcement="assertive"
                >{{ t('taskEntry.runError')
                }}<template #actions
                  ><AppButton variant="ghost" @click="runsQuery.refetch()">{{
                    t('projects.retry')
                  }}</AppButton></template
                ></AppFeedback
              >
              <AppFeedback v-else-if="runsQuery.isSuccess.value && !runs.length" class="app-card"
                >{{ t('taskEntry.noResults')
                }}<template #actions
                  ><AppButton
                    variant="ghost"
                    :to="{ name: 'snapshotRuns', params: { projectId, snapshotId: snapshot.id } }"
                    >{{ t('nav.classification') }}</AppButton
                  ></template
                ></AppFeedback
              >
              <ul class="task-options">
                <li v-for="entry in runs" :key="entry.id" class="task-option app-resource-card">
                  <div>
                    <h3>
                      {{
                        t('taskEntry.runTitle', {
                          date: d(new Date(entry.created_at), 'timestamp'),
                        })
                      }}
                    </h3>
                    <p>
                      <span>{{
                        entry.resolved_config.methods.map((method) => method.name).join(', ')
                      }}</span>
                      <span class="task-meta">{{ statusLabel(entry.status) }}</span>
                    </p>
                    <span v-if="working?.runId === entry.id" class="task-recommended">{{
                      t('taskEntry.recommended')
                    }}</span>
                  </div>
                  <AppButton
                    variant="ghost"
                    :to="{ query: { snapshot: snapshot.id, run: entry.id } }"
                    :aria-label="
                      t('taskEntry.selectRunNamed', {
                        date: d(new Date(entry.created_at), 'timestamp'),
                      })
                    "
                    >{{ t('taskEntry.select') }}</AppButton
                  >
                </li>
              </ul>
              <AppButton
                v-if="runsQuery.hasNextPage.value"
                variant="ghost"
                :disabled="runsQuery.isFetchingNextPage.value"
                @click="runsQuery.fetchNextPage()"
                >{{ t('taskEntry.moreRuns') }}</AppButton
              >
            </section>
            <section v-else-if="selectedRunId" aria-labelledby="task-results-title">
              <div class="task-context app-resource-card">
                <h2 id="task-results-title" ref="stepHeading" tabindex="-1">
                  {{ t('taskEntry.selectResult') }}
                </h2>
                <AppButton
                  variant="text"
                  :to="{ query: { snapshot: snapshot.id, evidence: '1' } }"
                  >{{ t('taskEntry.changeRun') }}</AppButton
                >
              </div>
              <AppFeedback
                v-if="runQuery.isPending.value || (run && resultsQuery.isPending.value)"
                class="app-card"
                announcement="polite"
                >{{ t('review.loading') }}</AppFeedback
              >
              <AppFeedback
                v-else-if="!run"
                class="app-card"
                tone="critical"
                announcement="assertive"
                >{{ t('taskEntry.selectionUnavailable')
                }}<template #actions
                  ><AppButton variant="ghost" @click="runQuery.refetch()">{{
                    t('projects.retry')
                  }}</AppButton></template
                ></AppFeedback
              >
              <template v-else>
                <p>
                  {{ t('taskEntry.runTitle', { date: d(new Date(run.created_at), 'timestamp') }) }}
                  <span class="task-meta">{{
                    run.resolved_config.methods.map((method) => method.name).join(', ')
                  }}</span>
                </p>
                <AppFeedback
                  v-if="resultsQuery.isError.value"
                  class="app-card"
                  tone="critical"
                  announcement="assertive"
                  >{{ t('taskEntry.resultError')
                  }}<template #actions
                    ><AppButton variant="ghost" @click="resultsQuery.refetch()">{{
                      t('projects.retry')
                    }}</AppButton></template
                  ></AppFeedback
                >
                <AppFeedback
                  v-else-if="resultsQuery.isSuccess.value && !results.length"
                  class="app-card"
                >
                  {{ t('taskEntry.noResults') }}
                </AppFeedback>
                <ul class="task-options">
                  <li
                    v-for="entry in results"
                    :key="entry.id"
                    class="task-option app-resource-card"
                  >
                    <div>
                      <h3>
                        {{
                          t('taskEntry.resultTitle', {
                            date: d(new Date(entry.created_at), 'timestamp'),
                          })
                        }}
                      </h3>
                      <p>
                        {{ entry.strategy }}
                        {{
                          t('taskEntry.methodCount', {
                            count: n(entry.method_execution_ids.length, 'integer'),
                          })
                        }}
                      </p>
                      <span v-if="working?.aggregationId === entry.id" class="task-recommended">{{
                        t('taskEntry.recommended')
                      }}</span>
                    </div>
                    <AppButton
                      variant="ghost"
                      :to="{
                        name: mode === 'game' ? 'game' : 'review',
                        params: { projectId, runId: run.id, aggregationId: entry.id },
                      }"
                      :aria-label="
                        t('taskEntry.openResultNamed', {
                          date: d(new Date(entry.created_at), 'timestamp'),
                        })
                      "
                      >{{
                        mode === 'game' ? t('taskEntry.openGame') : t('taskEntry.openReview')
                      }}</AppButton
                    >
                  </li>
                </ul>
                <AppButton
                  v-if="resultsQuery.hasNextPage.value"
                  variant="ghost"
                  :disabled="resultsQuery.isFetchingNextPage.value"
                  @click="resultsQuery.fetchNextPage()"
                  >{{ t('taskEntry.moreResults') }}</AppButton
                >
              </template>
            </section>
          </template>
        </template>
      </template>
    </template>
  </main>
</template>

<style scoped>
.task-meta {
  display: block;
  margin-block-start: var(--space-1);
}
.task-entry {
  container: task-entry / inline-size;
}
.task-option p,
.task-annotation-choice p {
  color: var(--text-secondary);
  max-inline-size: 70ch;
}
.task-entry section {
  margin-block-start: var(--space-6);
}
.task-entry h2 {
  font-size: var(--font-size-title);
  margin-block: 0 var(--space-4);
}
.task-options {
  list-style: none;
  margin: var(--space-4) 0;
  padding: 0;
  display: grid;
  gap: var(--space-3);
}
.task-option {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3) var(--space-6);
}
.task-option > div {
  min-inline-size: 0;
  flex: 1 1 22rem;
  overflow-wrap: anywhere;
}
.task-option h3 {
  font-size: var(--font-size-body-strong);
  margin: 0;
  font-weight: var(--weight-semibold);
}
.task-option p {
  margin: var(--space-2) 0 0;
}
.task-option-facts {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-2) var(--space-5);
  margin: var(--space-3) 0 0;
}
.task-option-facts > div {
  min-inline-size: 0;
}
.task-option-facts dt {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
.task-option-facts dd {
  margin: var(--space-1) 0 0;
  overflow-wrap: anywhere;
}
.task-recommended {
  display: inline-block;
  margin-block-start: var(--space-2);
  color: var(--accent);
  font-size: var(--font-size-small);
  font-weight: var(--weight-semibold);
}
.task-context,
.task-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}
.task-context {
  margin-block-end: var(--space-6);
}
.task-context p,
.task-context h2 {
  margin: 0;
  overflow-wrap: anywhere;
}
.task-actions {
  justify-content: flex-start;
}
.task-annotation-choice {
  margin-block: var(--space-6);
}
@container (min-width: 42rem) {
  .task-option-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
