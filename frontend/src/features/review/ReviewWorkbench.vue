<script setup lang="ts">
import { PhCaretDown, PhCaretUp } from '@phosphor-icons/vue'
import { computed, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useAggregation } from '@/features/runs/useAggregations'
import { useProject } from '@/features/projects/useProjects'
import { useMethodList } from '@/features/runs/useMethods'
import { useRun } from '@/features/runs/useRunDetail'
import { useImportedSnapshot } from '@/features/projects/useSnapshotData'

import ReviewDetail from './ReviewDetail.vue'
import ReviewBulkBar from './ReviewBulkBar.vue'
import ReviewFilterPanel from './ReviewFilterPanel.vue'
import ReviewList from './ReviewList.vue'
import ReviewQueueTabs from './ReviewQueueTabs.vue'
import {
  useReviewItemByPerson,
  useReviewItems,
  useReviewSummary,
  type ReviewItem,
} from './useReviewData'
import { queueCounts, useReviewFilters, type QueueCount, type QueueId } from './useReviewFilters'
import { isRecoverableReviewError, retainedReviewData } from './retainedReviewData'

const props = defineProps<{
  /** `review`: the D2 evidence queues. `people`: the whole register, in TEI order, for finding anybody. */
  mode: 'review' | 'people'
}>()

const { t, n, d } = useI18n()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')
const aggregationId = useRouteParam('aggregationId')

const isPeople = props.mode === 'people'
const filtersOpen = ref(false)
const { filters, person, setFilters, setQueue, selectPerson } = useReviewFilters(
  isPeople ? 'all' : undefined,
)

// Recording a decision is a project-scoped action from the reviewer role up (ADR-0033).
const project = useProject(projectId, isSignedIn)
const cache = useQueryClient()
const projectData = computed(() =>
  retainedReviewData(
    cache,
    ['projects', projectId.value, session.user?.id ?? 'anonymous'],
    session.canUsePrivateNavigation,
    project.status.value,
    project.data.value,
    project.error.value,
  ),
)
const canReview = computed(() => {
  const role = projectData.value?.current_user_role
  return role === 'reviewer' || role === 'operator'
})

const aggregation = useAggregation(aggregationId, isSignedIn)
const run = useRun(runId, isSignedIn)
const runData = computed(() =>
  retainedReviewData(
    cache,
    ['runs', runId.value],
    session.canUsePrivateNavigation && projectData.value?.id === projectId.value,
    run.status.value,
    run.data.value,
    run.error.value,
  ),
)
const aggregationData = computed(() =>
  retainedReviewData(
    cache,
    ['aggregations', aggregationId.value],
    session.canUsePrivateNavigation && projectData.value?.id === projectId.value,
    aggregation.status.value,
    aggregation.data.value,
    aggregation.error.value,
  ),
)
const snapshotId = computed(() =>
  runData.value?.id === runId.value ? runData.value.dataset_snapshot_id : '',
)
const snapshot = useImportedSnapshot(
  projectId,
  snapshotId,
  computed(() => isSignedIn.value && snapshotId.value !== ''),
)
const validContext = computed(
  () =>
    projectData.value?.id === projectId.value &&
    runData.value?.id === runId.value &&
    aggregationData.value?.id === aggregationId.value &&
    aggregationData.value.run_id === runId.value &&
    (!snapshot.isError.value || isRecoverableReviewError(snapshot.error.value)) &&
    snapshot.data.value?.id === snapshotId.value &&
    snapshot.data.value.project_id === projectId.value &&
    snapshot.data.value.status === 'ready',
)
// Certainty and agreement are immutable for a completed aggregation, and only a completed one has
// results to review; before that the screen says so instead of showing an empty queue.
const isCompleted = computed(
  () => validContext.value && aggregationData.value?.status === 'completed',
)
const contextFailed = computed(
  () =>
    project.isError.value ||
    run.isError.value ||
    aggregation.isError.value ||
    snapshot.isError.value,
)
const contextFresh = computed(
  () =>
    validContext.value &&
    !contextFailed.value &&
    !project.isFetching.value &&
    !run.isFetching.value &&
    !aggregation.isFetching.value &&
    !snapshot.isFetching.value,
)

const summary = useReviewSummary(aggregationId, isCompleted)
const methods = useMethodList(isSignedIn)
const methodNames = computed(() => (methods.data.value ?? []).map((method) => method.name))

const list = useReviewItems(aggregationId, filters, isCompleted)
const items = computed(() => list.data.value?.pages.flatMap((page) => page.items) ?? [])

// Bulk selection. It belongs to the list as it is now: another queue or another filter is another
// list, so the selection is dropped with it rather than silently applying to people out of view.
const ticked = ref<ReadonlySet<string>>(new Set())
watch([() => JSON.stringify(filters.value), aggregationId, () => session.user?.id], () => {
  ticked.value = new Set()
})
const tickedItems = computed(() => items.value.filter((item) => ticked.value.has(item.tei_id)))

function toggleTick(teiId: string, checked: boolean): void {
  const next = new Set(ticked.value)
  if (checked) next.add(teiId)
  else next.delete(teiId)
  ticked.value = next
}

function toggleAll(checked: boolean): void {
  ticked.value = checked ? new Set(items.value.map((item) => item.tei_id)) : new Set()
}

// People whose decision was saved leave the selection; the others stay, for another try.
function finishBulk(saved: string[]): void {
  const next = new Set(ticked.value)
  for (const teiId of saved) next.delete(teiId)
  ticked.value = next
}

// The counts on the queue cards come from the summary, never from the pages loaded so far.
const counts = computed<Record<QueueId, QueueCount> | null>(() => {
  const groups = summary.data.value?.groups
  return groups ? queueCounts(groups) : null
})

// The selected person is the list's item when it is on a loaded page; a deep link to somebody the
// list does not contain (another queue, another filter) is fetched by id instead.
const listed = computed(() => items.value.find((item) => item.tei_id === person.value) ?? null)
const fetched = useReviewItemByPerson(
  aggregationId,
  person,
  computed(() => isCompleted.value && person.value !== null && listed.value === null),
)
// A filter refetch briefly removes the list's item before its direct lookup resolves. Keep the
// same person's mounted detail during that gap, so a query-only filter cannot erase their draft.
const selectedItem = computed<ReviewItem | null>((previous) => {
  const current = listed.value ?? fetched.data.value
  if (
    current?.tei_id === person.value &&
    current.snapshot_id === snapshotId.value &&
    current.aggregation_execution_id === aggregationId.value
  )
    return current
  if (
    fetched.isPending.value &&
    previous &&
    previous.snapshot_id === snapshotId.value &&
    previous.tei_id === person.value &&
    previous.aggregation_execution_id === aggregationId.value
  )
    return previous
  return null
})
const decisionContextReady = computed(
  () => contextFresh.value && !list.isError.value && !fetched.isError.value,
)

type DetailNavigationDirection = 'previous' | 'next'

const detailNavigationPending = ref<DetailNavigationDirection | null>(null)
const detailNavigationFocusRequest = ref(0)
const detailNavigationFocusTarget = ref<DetailNavigationDirection | null>(null)
const detailNavigationFocusPerson = ref<string | null>(null)
const selectedIndex = computed(() => items.value.findIndex((item) => item.tei_id === person.value))
const detailNavigationBusy = computed(
  () => detailNavigationPending.value !== null || list.isFetchingNextPage.value,
)
const canNavigatePrevious = computed(() => selectedIndex.value > 0 && !detailNavigationBusy.value)
const canNavigateNext = computed(() => {
  const index = selectedIndex.value
  return (
    index >= 0 &&
    !detailNavigationBusy.value &&
    (index < items.value.length - 1 || list.hasNextPage.value)
  )
})

async function navigateDetail(direction: DetailNavigationDirection): Promise<void> {
  if (detailNavigationBusy.value) return

  const sourceId = person.value
  const index = selectedIndex.value
  if (sourceId === null || index < 0) return
  if (direction === 'previous' && index === 0) return
  if (direction === 'next' && index === items.value.length - 1 && !list.hasNextPage.value) return

  detailNavigationPending.value = direction
  try {
    let target: ReviewItem | undefined
    if (direction === 'previous') target = items.value[index - 1]
    else {
      target = items.value[index + 1]
      if (!target && list.hasNextPage.value) {
        await list.fetchNextPage()
        if (person.value !== sourceId) return
        const updatedIndex = items.value.findIndex((item) => item.tei_id === sourceId)
        target = updatedIndex === -1 ? undefined : items.value[updatedIndex + 1]
      }
    }
    if (!target) return

    await selectPerson(target.tei_id)
    if (person.value === target.tei_id) {
      detailNavigationFocusPerson.value = target.tei_id
      detailNavigationFocusTarget.value = direction
      detailNavigationFocusRequest.value += 1
    }
  } finally {
    detailNavigationPending.value = null
  }
}

function navigationFocusRestored(): void {
  detailNavigationFocusPerson.value = null
  detailNavigationFocusTarget.value = null
}

// With nothing selected, start on the first entry, so the detail column is never an empty stage.
watch(
  [items, person],
  ([current, selected]) => {
    const [first] = current
    if (selected === null && first) void selectPerson(first.tei_id)
  },
  { immediate: true },
)

const summaryLine = computed(() => {
  if (!aggregationData.value) return ''
  const count = summary.data.value?.result_count ?? 0
  return count === 1
    ? t('review.subtitleOne')
    : t('review.subtitleMany', { count: n(count, 'integer') })
})

const announce = computed(() =>
  list.isSuccess.value ? t('review.list.count', { count: n(items.value.length, 'integer') }) : '',
)
function retryContext(): void {
  void project.refetch()
  void run.refetch()
  void aggregation.refetch()
  if (snapshotId.value) void snapshot.refetch()
}
</script>

<template>
  <main class="review app-page-frame app-page-frame--dense">
    <header class="review-heading-row app-page-heading">
      <h1 class="review-title app-page-heading__title">
        {{ isPeople ? t('review.people.title') : t('review.title') }}
      </h1>
      <div v-if="isSignedIn" class="app-page-heading__actions">
        <AppButton
          v-if="isPeople"
          variant="ghost"
          :to="{
            name: canReview ? 'projectAnnotation' : 'projectSnapshots',
            params: { projectId },
          }"
          >{{ t('taskEntry.changeSelection') }}</AppButton
        >
        <AppButton
          v-else
          id="review-filter-toggle"
          variant="ghost"
          :aria-expanded="filtersOpen"
          aria-controls="review-filter-panel"
          @click="filtersOpen = !filtersOpen"
        >
          {{ t('review.filters.title') }}
          <PhCaretUp v-if="filtersOpen" :size="16" aria-hidden="true" />
          <PhCaretDown v-else :size="16" aria-hidden="true" />
        </AppButton>
      </div>
    </header>

    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('review.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="review-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('review.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <p v-if="aggregation.isPending.value" role="status">{{ t('review.loading') }}</p>
      <div v-else-if="aggregation.isError.value && !validContext" class="review-load-error">
        <p role="alert">{{ t('review.aggregationLoadError') }}</p>
        <AppButton class="review-retry" type="button" @click="() => aggregation.refetch()">
          {{ t('review.retry') }}
        </AppButton>
      </div>
      <p
        v-else-if="
          project.isPending.value || run.isPending.value || (snapshotId && snapshot.isPending.value)
        "
        role="status"
      >
        {{ t('review.loading') }}
      </p>
      <div v-else-if="!validContext" class="review-load-error">
        <p role="alert">{{ t('taskEntry.selectionUnavailable') }}</p>
        <AppButton variant="ghost" @click="retryContext">{{ t('review.retry') }}</AppButton>
      </div>
      <p v-else-if="!isCompleted" class="review-not-ready" role="status">
        {{ t('review.notCompleted') }}
      </p>
      <template v-else>
        <div v-if="contextFailed" class="review-load-error">
          <p role="alert">{{ t('review.refreshError') }}</p>
          <AppButton variant="ghost" @click="retryContext">{{ t('review.retry') }}</AppButton>
        </div>
        <details
          v-if="snapshot.data.value && run.data.value && aggregation.data.value"
          class="review-context"
        >
          <summary class="review-context-summary">{{ summaryLine }}</summary>
          <div class="review-context-content">
            <h2 id="review-context-heading" class="review-context-title">
              {{ t('review.context.title') }}
            </h2>
            <ol class="review-context-steps" aria-labelledby="review-context-heading">
              <li class="review-context-step">
                <h3>{{ t('review.context.dataset') }}</h3>
                <time :datetime="snapshot.data.value.created_at">
                  {{ d(new Date(snapshot.data.value.created_at), 'timestamp') }}
                </time>
                <p>{{ t('review.context.datasetHint') }}</p>
              </li>
              <li class="review-context-step">
                <h3>{{ t('review.context.suggestions') }}</h3>
                <time :datetime="run.data.value.created_at">
                  {{ d(new Date(run.data.value.created_at), 'timestamp') }}
                </time>
                <p>{{ t('review.context.suggestionsHint') }}</p>
              </li>
              <li class="review-context-step">
                <h3>{{ t('review.context.result') }}</h3>
                <RouterLink
                  class="review-context-link"
                  :to="{ name: 'aggregationDetail', params: { projectId, runId, aggregationId } }"
                >
                  <time :datetime="aggregation.data.value.created_at">
                    {{ d(new Date(aggregation.data.value.created_at), 'timestamp') }}
                  </time>
                </RouterLink>
                <p>
                  {{
                    t('review.context.resultHint', {
                      strategy: aggregation.data.value.strategy ?? '',
                    })
                  }}
                </p>
              </li>
            </ol>
          </div>
        </details>
        <p v-if="isPeople" class="review-subtitle">{{ t('review.people.hint') }}</p>
        <ReviewQueueTabs v-else :queue="filters.queue" :counts="counts" @select="setQueue" />
        <template v-if="!isPeople">
          <div v-show="filtersOpen" id="review-filter-panel" class="review-filter-panel">
            <ReviewFilterPanel
              layout="panel"
              :filters="filters"
              :method-names="methodNames"
              @update="setFilters"
            />
          </div>
        </template>

        <p class="review-announce" role="status">{{ announce }}</p>

        <div
          class="review-grid"
          :class="isPeople ? 'review-grid--with-filter-column' : 'review-grid--review'"
        >
          <section
            v-if="isPeople"
            class="review-column review-filter-column"
            aria-labelledby="review-filter-heading"
          >
            <h2 id="review-filter-heading" class="review-visually-hidden">
              {{ t('review.filters.title') }}
            </h2>
            <ReviewFilterPanel
              :simple="isPeople"
              :filters="filters"
              :method-names="methodNames"
              @update="setFilters"
            />
          </section>

          <section class="review-column" aria-labelledby="review-list-heading">
            <h2 id="review-list-heading" class="review-column-title">
              {{ t('review.list.title') }}
            </h2>
            <ReviewBulkBar
              v-if="canReview"
              :key="aggregationId"
              :items="tickedItems"
              :loaded-count="items.length"
              :context-ready="decisionContextReady"
              @toggle-all="toggleAll"
              @clear="toggleAll(false)"
              @finished="finishBulk"
            />
            <ReviewList
              :selectable="canReview"
              :ticked="ticked"
              :items="items"
              :selected="person"
              :loading="list.isPending.value"
              :failed="list.isError.value"
              :has-more="list.hasNextPage.value"
              :loading-more="list.isFetchingNextPage.value"
              @select="selectPerson"
              @toggle="toggleTick"
              @load-more="() => list.fetchNextPage()"
              @retry="() => list.refetch()"
            />
          </section>

          <section class="review-column" aria-labelledby="review-detail-heading">
            <h2 id="review-detail-heading" class="review-visually-hidden">
              {{ t('review.detail.title') }}
            </h2>
            <ReviewDetail
              v-if="selectedItem"
              :key="`${session.user?.id}:${aggregationId}:${selectedItem.tei_id}`"
              :item="selectedItem"
              :can-review="canReview"
              :context-ready="decisionContextReady"
              :can-previous="canNavigatePrevious"
              :can-next="canNavigateNext"
              :navigation-busy="detailNavigationBusy"
              :navigation-focus-request="detailNavigationFocusRequest"
              :navigation-focus-person="detailNavigationFocusPerson"
              :navigation-focus-target="detailNavigationFocusTarget"
              @navigation-focus-restored="navigationFocusRestored"
              @previous="navigateDetail('previous')"
              @next="navigateDetail('next')"
            />
            <p v-else-if="fetched.isPending.value && person" role="status">
              {{ t('review.loading') }}
            </p>
            <p v-else-if="person" class="review-muted">{{ t('review.detail.notFound') }}</p>
            <p v-else class="review-muted">{{ t('review.detail.none') }}</p>
          </section>
        </div>
      </template>
    </template>
  </main>
</template>

<style scoped>
.review-heading-row {
  margin-block-end: 0;
}

.review-context {
  border-block: 1px solid var(--grid);
}

.review-context-summary {
  padding-block: var(--space-3);
  cursor: pointer;
  color: var(--text-secondary);
  font-weight: var(--weight-semibold);
}

.review-context-summary::marker {
  color: var(--accent);
}

.review-context[open] .review-context-summary {
  border-bottom: 1px solid var(--grid);
}

.review-context-content {
  padding-block: var(--space-3);
}

.review-context-title {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.review-context-steps {
  display: grid;
  gap: var(--space-3);
  margin: var(--space-2) 0 0;
  padding-inline-start: var(--space-5);
}

.review-context-step {
  min-width: 0;
  padding-inline-start: var(--space-1);
}

.review-context-step::marker {
  color: var(--accent);
  font-weight: var(--weight-semibold);
}

.review-context-step h3,
.review-context-step p {
  margin: 0;
}

.review-context-step h3 {
  font-size: var(--font-size-body);
  font-weight: var(--weight-semibold);
}

.review-context-step time,
.review-context-step p {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
.review {
  container: review-workbench / inline-size;
  overflow-wrap: anywhere;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
}

.review-context-link {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.review-subtitle,
.review-muted,
.review-not-ready {
  margin: 0;
  color: var(--text-secondary);
}

.review-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.review-load-error p {
  margin: 0;
  color: var(--critical-text);
}

/* Queue and detail use the full workbench once review filters move into the disclosure above. */
.review-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-4);
  align-items: start;
}

@container review-workbench (min-width: 42rem) {
  .review-context-steps {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@container review-workbench (min-width: 42rem) {
  .review-grid--review {
    grid-template-columns: minmax(18rem, 1fr) minmax(22rem, 2fr);
  }
}

@container review-workbench (min-width: 57rem) {
  .review-grid--with-filter-column {
    grid-template-columns: 15rem minmax(18rem, 1fr) minmax(22rem, 1.4fr);
  }
}

.review-filter-panel,
.review-column {
  min-width: 0;
  padding: var(--page-gutter);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.review-column-title {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.review-visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.review-announce {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
</style>
