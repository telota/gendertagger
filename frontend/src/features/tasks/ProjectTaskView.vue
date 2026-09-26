<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useProjectIdentity } from '@/app/useProjectIdentity'
import { useRequireSession } from '@/composables/useRequireSession'
import { hasProjectRole } from '@/features/projects/projectRoles'
import { useImportedSnapshot } from '@/features/projects/useSnapshotData'
import { useStatusLabel } from '@/features/runs/useStatusLabel'

import {
  useTaskSnapshots,
  useTaskRuns,
  useTaskResults,
  useTaskRun,
  useProjectReviewResults,
  useWorkingSelection,
  type TaskMode,
} from './useTaskData'

const props = defineProps<{ mode: TaskMode }>()
const { t, d, n } = useI18n()
const route = useRoute()
const router = useRouter()
const statusLabel = useStatusLabel()
const { session, isSignedIn, retrySession } = useRequireSession()
const { projectId, project, query: projectQuery } = useProjectIdentity()
const canEnter = computed(
  () =>
    project.value !== null &&
    (props.mode === 'classification' ||
      hasProjectRole(project.value.current_user_role, 'reviewer')),
)
const title = computed(() =>
  props.mode === 'classification'
    ? t('runs.title')
    : props.mode === 'review'
      ? t('review.title')
      : t('review.people.title'),
)
const description = computed(() =>
  props.mode === 'classification'
    ? t('taskEntry.classificationHint')
    : props.mode === 'review'
      ? t('taskEntry.reviewHint')
      : t('taskEntry.annotationHint'),
)
const selectedSnapshotId = computed(() =>
  props.mode !== 'classification' && typeof route.query.snapshot === 'string'
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
  computed(() => props.mode === 'review'),
  computed(() => canEnter.value && props.mode !== 'review' && !selectedSnapshotId.value),
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
  computed(() => canEnter.value && props.mode === 'review' && !selectedSnapshotId.value),
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
  <main class="task-entry">
    <header class="task-heading">
      <h1>{{ title }}</h1>
      <p>{{ description }}</p>
    </header>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      announcement="polite"
      >{{ t('review.loading') }}</AppFeedback
    >
    <AppFeedback v-else-if="session.status === 'error'" tone="critical" announcement="assertive">
      {{ t('projects.sessionLoadError') }}
      <template #actions
        ><AppButton variant="ghost" @click="retrySession">{{
          t('projects.retry')
        }}</AppButton></template
      >
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <AppFeedback v-if="projectQuery.isPending.value" announcement="polite">{{
        t('projects.loading')
      }}</AppFeedback>
      <AppFeedback v-else-if="projectQuery.isError.value" tone="critical" announcement="assertive">
        {{ t('data.projectLoadError') }}
        <template #actions
          ><AppButton variant="ghost" @click="projectQuery.refetch()">{{
            t('projects.retry')
          }}</AppButton></template
        >
      </AppFeedback>
      <AppFeedback v-else-if="!canEnter">{{ t('taskEntry.noPermission') }}</AppFeedback>
      <template v-else>
        <AppFeedback
          v-if="workingId && workingQuery.isError.value"
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
          v-if="mode === 'review' && !selectedSnapshotId"
          aria-labelledby="task-review-results-title"
        >
          <h2 id="task-review-results-title" ref="stepHeading" tabindex="-1">
            {{ t('taskEntry.reviewResultsTitle') }}
          </h2>
          <AppFeedback v-if="reviewResultsQuery.isPending.value" announcement="polite">{{
            t('review.loading')
          }}</AppFeedback>
          <AppFeedback
            v-if="reviewResultsQuery.isError.value"
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
          <AppFeedback v-else-if="reviewResultsQuery.isSuccess.value && !reviewResults.length">
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
            <li v-for="entry in reviewResults" :key="entry.aggregation.id" class="task-option">
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
                  name: 'review',
                  params: { projectId, runId: entry.run.id, aggregationId: entry.aggregation.id },
                }"
                :aria-label="
                  t('taskEntry.openResultNamed', {
                    date: d(new Date(entry.aggregation.created_at), 'timestamp'),
                  })
                "
                >{{ t('taskEntry.openReview') }}</AppButton
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
        <section v-else-if="!selectedSnapshotId" aria-labelledby="task-snapshots-title">
          <h2 id="task-snapshots-title" ref="stepHeading" tabindex="-1">
            {{ t('taskEntry.selectSnapshot') }}
          </h2>
          <AppFeedback v-if="snapshotsQuery.isPending.value" announcement="polite">{{
            t('data.loading')
          }}</AppFeedback>
          <AppFeedback v-if="snapshotsQuery.isError.value" tone="critical" announcement="assertive">
            {{ t('taskEntry.snapshotError') }}
            <template #actions
              ><AppButton variant="ghost" @click="snapshotsQuery.refetch()">{{
                t('projects.retry')
              }}</AppButton></template
            >
          </AppFeedback>
          <AppFeedback v-else-if="snapshotsQuery.isSuccess.value && !snapshots.length">
            {{ mode === 'review' ? t('taskEntry.noReviewSnapshots') : t('taskEntry.noSnapshots') }}
            <template #actions
              ><AppButton
                variant="ghost"
                :to="{
                  name: mode === 'review' ? 'projectClassification' : 'projectSnapshots',
                  params: { projectId },
                }"
                >{{ mode === 'review' ? t('nav.classification') : t('nav.data') }}</AppButton
              ></template
            >
          </AppFeedback>
          <ul class="task-options">
            <li v-for="entry in snapshots" :key="entry.id" class="task-option">
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
        <template v-else>
          <AppFeedback v-if="snapshotQuery.isPending.value" announcement="polite">{{
            t('data.loading')
          }}</AppFeedback>
          <AppFeedback v-else-if="!snapshot" tone="critical" announcement="assertive">
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
            <div class="task-context">
              <p>
                {{
                  t('data.snapshotTitle', { date: d(new Date(snapshot.created_at), 'timestamp') })
                }}
              </p>
              <AppButton variant="text" :to="{ query: {} }">{{
                t('taskEntry.changeSnapshot')
              }}</AppButton>
            </div>
            <div v-if="mode === 'annotation'" class="task-annotation-choice">
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
              <AppFeedback v-if="runsQuery.isPending.value" announcement="polite">{{
                t('review.loading')
              }}</AppFeedback>
              <AppFeedback v-if="runsQuery.isError.value" tone="critical" announcement="assertive"
                >{{ t('taskEntry.runError')
                }}<template #actions
                  ><AppButton variant="ghost" @click="runsQuery.refetch()">{{
                    t('projects.retry')
                  }}</AppButton></template
                ></AppFeedback
              >
              <AppFeedback v-else-if="runsQuery.isSuccess.value && !runs.length"
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
                <li v-for="entry in runs" :key="entry.id" class="task-option">
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
              <div class="task-context">
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
                announcement="polite"
                >{{ t('review.loading') }}</AppFeedback
              >
              <AppFeedback v-else-if="!run" tone="critical" announcement="assertive"
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
                  tone="critical"
                  announcement="assertive"
                  >{{ t('taskEntry.resultError')
                  }}<template #actions
                    ><AppButton variant="ghost" @click="resultsQuery.refetch()">{{
                      t('projects.retry')
                    }}</AppButton></template
                  ></AppFeedback
                >
                <AppFeedback v-else-if="resultsQuery.isSuccess.value && !results.length">{{
                  t('taskEntry.noResults')
                }}</AppFeedback>
                <ul class="task-options">
                  <li v-for="entry in results" :key="entry.id" class="task-option">
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
                        name: mode === 'review' ? 'review' : 'people',
                        params: { projectId, runId: run.id, aggregationId: entry.id },
                      }"
                      :aria-label="
                        t('taskEntry.openResultNamed', {
                          date: d(new Date(entry.created_at), 'timestamp'),
                        })
                      "
                      >{{
                        mode === 'review'
                          ? t('taskEntry.openReview')
                          : t('taskEntry.openAnnotation')
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
  flex: 1;
  inline-size: 100%;
  min-inline-size: 0;
  max-inline-size: 60rem;
  margin-inline: auto;
  padding: var(--space-8) var(--page-gutter);
}
.task-heading {
  margin-block-end: var(--space-8);
}
.task-heading h1 {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
  font-weight: var(--weight-semibold);
}
.task-heading p,
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
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
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
  border-block-end: 1px solid var(--border);
  padding-block-end: var(--space-3);
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
