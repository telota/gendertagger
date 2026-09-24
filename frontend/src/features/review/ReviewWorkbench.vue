<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useAggregation } from '@/features/runs/useAggregations'
import { useProject } from '@/features/projects/useProjects'
import { useMethodList } from '@/features/runs/useMethods'

import ReviewDetail from './ReviewDetail.vue'
import ReviewBulkBar from './ReviewBulkBar.vue'
import ReviewFilterPanel from './ReviewFilterPanel.vue'
import ReviewList from './ReviewList.vue'
import ReviewQueueTabs from './ReviewQueueTabs.vue'
import { useReviewItemByPerson, useReviewItems, useReviewSummary } from './useReviewData'
import {
  QUEUE_TIERS,
  QUEUES,
  useReviewFilters,
  type QueueCount,
  type QueueId,
} from './useReviewFilters'

const props = defineProps<{
  /** `review`: the D2 evidence queues. `people`: the whole register, in TEI order, for finding anybody. */
  mode: 'review' | 'people'
}>()

const { t, n } = useI18n()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')
const aggregationId = useRouteParam('aggregationId')

const isPeople = props.mode === 'people'
const { filters, person, setFilters, setQueue, selectPerson } = useReviewFilters(
  isPeople ? 'all' : undefined,
)

// Recording a decision is a project-scoped action from the reviewer role up (ADR-0033).
const project = useProject(projectId, isSignedIn)
const canReview = computed(() => {
  const role = project.data.value?.current_user_role
  return role === 'reviewer' || role === 'operator'
})

const aggregation = useAggregation(aggregationId, isSignedIn)
// Certainty and agreement are immutable for a completed aggregation, and only a completed one has
// results to review; before that the screen says so instead of showing an empty queue.
const isCompleted = computed(() => aggregation.data.value?.status === 'completed')

const summary = useReviewSummary(aggregationId, isCompleted)
const methods = useMethodList(isSignedIn)
const methodNames = computed(() => (methods.data.value ?? []).map((method) => method.name))

const list = useReviewItems(aggregationId, filters, isCompleted)
const items = computed(() => list.data.value?.pages.flatMap((page) => page.items) ?? [])

// Bulk selection. It belongs to the list as it is now: another queue or another filter is another
// list, so the selection is dropped with it rather than silently applying to people out of view.
const ticked = ref<ReadonlySet<string>>(new Set())
watch(
  () => JSON.stringify(filters.value),
  () => {
    ticked.value = new Set()
  },
)
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
  if (!groups) return null
  const result = {} as Record<QueueId, QueueCount>
  for (const queue of QUEUES) {
    const tiers = QUEUE_TIERS[queue]
    const inQueue = groups.filter(
      (group) => tiers.length === 0 || tiers.includes(group.certainty_tier),
    )
    result[queue] = {
      total: inQueue.reduce((sum, group) => sum + group.result_count, 0),
      open: inQueue
        .filter((group) => group.workflow_state === 'unreviewed')
        .reduce((sum, group) => sum + group.result_count, 0),
    }
  }
  return result
})

// The selected person is the list's item when it is on a loaded page; a deep link to somebody the
// list does not contain (another queue, another filter) is fetched by id instead.
const listed = computed(() => items.value.find((item) => item.tei_id === person.value) ?? null)
const fetched = useReviewItemByPerson(
  aggregationId,
  person,
  computed(() => isCompleted.value && person.value !== null && listed.value === null),
)
const selectedItem = computed(() => listed.value ?? fetched.data.value ?? null)

// With nothing selected, start on the first entry, so the detail column is never an empty stage.
watch(
  [items, person],
  ([current, selected]) => {
    const [first] = current
    if (selected === null && first) selectPerson(first.tei_id)
  },
  { immediate: true },
)

const summaryLine = computed(() => {
  const data = aggregation.data.value
  if (!data) return ''
  return t('review.subtitle', {
    strategy: data.strategy ?? '',
    count: n(summary.data.value?.result_count ?? 0, 'integer'),
  })
})

const announce = computed(() =>
  list.isSuccess.value ? t('review.list.count', { count: n(items.value.length, 'integer') }) : '',
)
</script>

<template>
  <main class="review">
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('review.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="review-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('review.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <RouterLink
        class="review-back"
        :to="{ name: 'aggregationDetail', params: { projectId, runId, aggregationId } }"
      >
        {{ t('review.back') }}
      </RouterLink>
      <h1 class="review-title">{{ isPeople ? t('review.people.title') : t('review.title') }}</h1>

      <p v-if="aggregation.isPending.value" role="status">{{ t('review.loading') }}</p>
      <div v-else-if="aggregation.isError.value" class="review-load-error">
        <p role="alert">{{ t('review.aggregationLoadError') }}</p>
        <AppButton class="review-retry" type="button" @click="() => aggregation.refetch()">
          {{ t('review.retry') }}
        </AppButton>
      </div>
      <p v-else-if="!isCompleted" class="review-not-ready" role="status">
        {{ t('review.notCompleted') }}
      </p>
      <template v-else>
        <p class="review-subtitle">{{ summaryLine }}</p>
        <p v-if="isPeople" class="review-subtitle">{{ t('review.people.hint') }}</p>
        <ReviewQueueTabs v-else :queue="filters.queue" :counts="counts" @select="setQueue" />

        <p class="review-announce" role="status">{{ announce }}</p>

        <div class="review-grid">
          <section class="review-column" aria-labelledby="review-filter-heading">
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
              :items="tickedItems"
              :loaded-count="items.length"
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
            <ReviewDetail v-if="selectedItem" :item="selectedItem" :can-review="canReview" />
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
.review {
  padding: var(--space-8) var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
}

.review-back {
  align-self: flex-start;
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.review-title {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
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
  color: var(--critical);
}

/* Filters | queue | detail on wide windows; stacked when there is no room for three columns. */
.review-grid {
  display: grid;
  grid-template-columns: 15rem minmax(18rem, 1fr) minmax(22rem, 1.4fr);
  gap: var(--space-4);
  align-items: start;
}

@media (max-width: 68rem) {
  .review-grid {
    grid-template-columns: 1fr;
  }
}

.review-column {
  min-width: 0;
  padding: var(--space-4);
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
