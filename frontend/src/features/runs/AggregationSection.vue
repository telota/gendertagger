<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'
import { useProject } from '@/composables/useProjects'

import AggregationItem from './AggregationItem.vue'
import {
  AGGREGATABLE_EXECUTION_STATUSES,
  isTerminalAggregation,
  useAggregationList,
  useCreateAggregation,
  type AggregationCreated,
} from '@/composables/useAggregations'
import { useStatusLabel } from '@/composables/useStatusLabel'
import type { components } from '@/api/schema'

type MethodExecutionSummary = components['schemas']['MethodExecutionSummary']
type Run = components['schemas']['Run']

const props = defineProps<{
  projectId: string
  run: Run
  executions: readonly MethodExecutionSummary[]
}>()

const { t, d, n } = useI18n()
const label = useStatusLabel()

const runId = computed(() => props.run.id)
const list = useAggregationList(runId)
const aggregations = computed(() => list.data.value?.pages.flatMap((page) => page.items) ?? [])

const project = useProject(computed(() => props.projectId))
// Creating an aggregation is a project-scoped operator action, like starting a run.
const canOperate = computed(() => project.data.value?.current_user_role === 'operator')

const currentAggregation = computed(() => {
  const items = aggregations.value
  const workingId = project.data.value?.working_aggregation_execution_id
  const working = workingId ? items.find((aggregation) => aggregation.id === workingId) : undefined
  return (
    working ??
    items.find(
      (aggregation) => aggregation.status !== 'failed' && aggregation.status !== 'cancelled',
    ) ??
    items[0] ??
    null
  )
})
const aggregationHistory = computed(() => {
  const currentId = currentAggregation.value?.id
  return currentId
    ? aggregations.value.filter((aggregation) => aggregation.id !== currentId)
    : aggregations.value
})
const currentTitle = computed(() => {
  const current = currentAggregation.value
  if (current === null) return ''
  if (project.data.value?.working_aggregation_execution_id === current.id) {
    return t('aggregations.currentWorking')
  }
  if (current.status === 'failed' || current.status === 'cancelled') {
    return t('aggregations.latestAttempt')
  }
  return t('aggregations.latestResult')
})

function historyTitle(createdAt: string): string {
  return t('aggregations.item.titleWithDate', {
    date: d(new Date(createdAt), 'timestamp'),
  })
}

const aggregatable = computed(() =>
  props.executions.filter((execution) => AGGREGATABLE_EXECUTION_STATUSES.has(execution.status)),
)
const runSucceeded = computed(
  () => props.run.status === 'completed' || props.run.status === 'completed_with_errors',
)

const create = useCreateAggregation()
const attempt = ref<'auto' | 'manual' | null>(null)
const lastResult = ref<AggregationCreated | null>(null)
const selected = ref<Record<string, boolean>>({})
const savedSelection = ref<Record<string, boolean>>({})
let generation = 0

async function createFor(ids: readonly string[], kind: 'auto' | 'manual'): Promise<void> {
  const requestGeneration = generation
  const submittedSelection = Object.fromEntries(
    aggregatable.value.map((execution) => [execution.id, ids.includes(execution.id)]),
  )
  attempt.value = kind
  lastResult.value = null
  try {
    const result = await create.mutateAsync({
      runId: props.run.id,
      methodExecutionIds: ids,
      strategy: 'reference_v1',
    })
    if (requestGeneration !== generation) return
    lastResult.value = result
    if (kind === 'manual') Object.assign(savedSelection.value, submittedSelection)
  } catch {
    // create.isError/.error already reflect this; the section shows it beside the list.
  }
}

// D4: when a run has finished successfully and nothing usable exists yet, create the default
// `reference_v1` aggregation over every completed execution. The server makes this idempotent
// (ADR-0034), so a reload cannot duplicate it, and it must fail visibly when the selection is not
// aggregatable, which the error below does. Once per run per visit: a failed attempt is shown, not
// retried in a loop.
const autoAttemptedFor = ref<string | null>(null)
const shouldAutoCreate = computed(
  () =>
    canOperate.value &&
    runSucceeded.value &&
    list.isSuccess.value &&
    aggregatable.value.length > 0 &&
    autoAttemptedFor.value !== props.run.id &&
    !aggregations.value.some(
      (aggregation) => aggregation.status !== 'failed' && aggregation.status !== 'cancelled',
    ),
)
watch(
  shouldAutoCreate,
  (yes) => {
    if (!yes) return
    autoAttemptedFor.value = props.run.id
    void createFor(
      aggregatable.value.map((execution) => execution.id),
      'auto',
    )
  },
  { immediate: true },
)

watch(
  [() => list.isSuccess.value, currentAggregation, aggregatable],
  ([isReady, current, available]) => {
    if (!isReady || Object.keys(selected.value).length > 0) return
    const currentSelection = current ? new Set(current.method_execution_ids) : null
    const initial = Object.fromEntries(
      available.map((execution) => [execution.id, currentSelection?.has(execution.id) ?? true]),
    )
    selected.value = initial
    savedSelection.value = { ...initial }
  },
  { immediate: true },
)

// The advanced path starts from the visible current selection. Operators can choose another exact
// execution set without re-running methods; the server remains authoritative for strategy validity.
const selectedIds = computed(() =>
  aggregatable.value
    .filter((execution) => selected.value[execution.id] ?? true)
    .map((execution) => execution.id),
)
const canSubmit = computed(() => selectedIds.value.length > 0 && !create.isPending.value)

useDraftRegistration(
  () =>
    aggregatable.value.some(
      (execution) =>
        (selected.value[execution.id] ?? true) !== (savedSelection.value[execution.id] ?? true),
    ),
  () => {
    generation += 1
    selected.value = {}
    savedSelection.value = {}
    attempt.value = null
    lastResult.value = null
  },
)
onScopeDispose(() => {
  generation += 1
})

function submitManual(): void {
  if (!canSubmit.value) return
  void createFor(selectedIds.value, 'manual')
}

const errorText = computed(() => {
  const error = create.error.value
  if (attempt.value === null || !create.isError.value || error === null) return ''
  if (error instanceof ApiError && error.code === 'resource_conflict') {
    return attempt.value === 'auto'
      ? t('aggregations.errors.autoNotAggregatable')
      : t('aggregations.errors.notAggregatable')
  }
  if (error instanceof ApiError && error.code === 'network_error') {
    return t('aggregations.errors.network')
  }
  return t('aggregations.errors.generic')
})

const reusedId = computed(() => (lastResult.value?.reused ? lastResult.value.aggregation.id : null))
const hasLive = computed(() => aggregations.value.some((item) => !isTerminalAggregation(item)))

function loadMore(): void {
  void list.fetchNextPage()
}
</script>

<template>
  <section class="aggregations" aria-labelledby="aggregations-heading">
    <div class="aggregations-header">
      <h2 id="aggregations-heading" class="aggregations-title">{{ t('aggregations.title') }}</h2>
      <p class="aggregations-hint">{{ t('aggregations.hint') }}</p>
    </div>

    <p v-if="!runSucceeded" class="aggregations-waiting app-card">
      {{ t('aggregations.waitingForRun') }}
    </p>

    <p v-if="list.isPending.value" class="app-card" role="status">{{ t('runs.loading') }}</p>
    <div v-else-if="list.isError.value" class="aggregations-load-error app-card">
      <p role="alert">{{ t('aggregations.loadError') }}</p>
      <AppButton class="aggregations-retry" type="button" @click="() => list.refetch()">
        {{ t('runs.retry') }}
      </AppButton>
    </div>
    <template v-else>
      <p
        v-if="aggregations.length === 0 && !(create.isPending.value && attempt === 'auto')"
        class="aggregations-empty app-card"
      >
        {{ t('aggregations.empty') }}
      </p>

      <ul v-if="currentAggregation" class="aggregations-items">
        <AggregationItem
          :aggregation="currentAggregation"
          :project-id="projectId"
          :executions="executions"
          :title="currentTitle"
          featured
        />
      </ul>

      <details v-if="aggregationHistory.length > 0" class="aggregations-history">
        <summary>
          {{
            t('aggregations.historyWithCount', {
              count: n(aggregationHistory.length, 'integer'),
            })
          }}
        </summary>
        <ul class="aggregations-items aggregations-items--history">
          <AggregationItem
            v-for="aggregation in aggregationHistory"
            :key="aggregation.id"
            :aggregation="aggregation"
            :project-id="projectId"
            :executions="executions"
            :title="historyTitle(aggregation.created_at)"
          />
        </ul>
        <AppButton
          v-if="list.hasNextPage.value"
          class="aggregations-load-more"
          type="button"
          @click="loadMore"
        >
          {{ t('runs.loadMore') }}
        </AppButton>
      </details>
      <AppButton
        v-else-if="list.hasNextPage.value"
        class="aggregations-load-more"
        type="button"
        @click="loadMore"
      >
        {{ t('runs.loadMore') }}
      </AppButton>
    </template>

    <p class="aggregations-live" role="status">
      {{
        create.isPending.value && attempt === 'auto'
          ? t('aggregations.autoCreating')
          : hasLive
            ? t('aggregations.inProgress')
            : ''
      }}
    </p>
    <p v-if="errorText" role="alert" class="aggregations-error app-card">{{ errorText }}</p>
    <p v-if="reusedId" class="aggregations-reused app-card" role="status">
      {{ t('aggregations.reused') }}
      <RouterLink
        class="aggregations-reused-link"
        :to="{
          name: 'aggregationDetail',
          params: { projectId, runId: run.id, aggregationId: reusedId },
        }"
      >
        {{ t('aggregations.item.open') }}
      </RouterLink>
    </p>

    <details v-if="canOperate && runSucceeded" class="aggregations-advanced app-card">
      <summary>{{ t('aggregations.advanced.title') }}</summary>
      <form class="aggregations-form" novalidate @submit.prevent="submitManual">
        <p class="aggregations-hint">{{ t('aggregations.advanced.hint') }}</p>
        <p class="aggregations-strategy">
          {{
            t('aggregations.advanced.strategy', {
              strategy: t('aggregations.item.referenceStrategy'),
            })
          }}
        </p>
        <fieldset class="aggregations-selection">
          <legend>{{ t('aggregations.advanced.selection') }}</legend>
          <div
            v-for="execution in aggregatable"
            :key="execution.id"
            class="aggregations-selection-row"
          >
            <input
              :id="`aggregate-${execution.id}`"
              type="checkbox"
              :checked="selected[execution.id] ?? true"
              @change="selected[execution.id] = ($event.target as HTMLInputElement).checked"
            />
            <label :for="`aggregate-${execution.id}`">
              <span>{{ execution.method_name }}</span>
              <span class="aggregations-method-status">{{ label(execution.status) }}</span>
            </label>
          </div>
        </fieldset>
        <AppButton class="aggregations-submit" type="submit" :disabled="!canSubmit">
          {{
            create.isPending.value
              ? t('aggregations.advanced.submitting')
              : t('aggregations.advanced.submit')
          }}
        </AppButton>
      </form>
    </details>
  </section>
</template>

<style scoped>
.aggregations {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
  width: 100%;
}

.aggregations-header {
  display: grid;
  gap: var(--space-1);
}

.aggregations-title {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.aggregations-hint,
.aggregations-waiting,
.aggregations-empty,
.aggregations-live,
.aggregations-strategy {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.aggregations-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.aggregations-load-error p,
.aggregations-error {
  margin: 0;
  color: var(--critical-text);
}

.aggregations-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
  margin: 0;
  padding: 0;
  list-style: none;
}

.aggregations-history {
  width: 100%;
}

.aggregations-history > summary,
.aggregations-advanced > summary {
  display: inline-flex;
  min-block-size: 2rem;
  align-items: center;
  gap: var(--space-1);
  cursor: pointer;
  font-weight: var(--weight-semibold);
}

.aggregations-history[open] > summary {
  margin-bottom: var(--space-3);
}

.aggregations-items--history {
  padding-left: var(--space-3);
  border-left: 1px solid var(--border);
}

.aggregations-load-more {
  margin-top: var(--space-3);
}

.aggregations-reused {
  margin: 0;
}

.aggregations-reused-link {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.aggregations-advanced {
  width: 100%;
}

.aggregations-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.aggregations-selection {
  width: 100%;
  margin: 0;
  padding: 0;
  border: 0;
}

.aggregations-selection legend {
  padding: 0;
  font-weight: var(--weight-semibold);
}

.aggregations-selection-row {
  display: flex;
  min-block-size: 2.5rem;
  align-items: center;
  gap: var(--space-2);
}

.aggregations-selection-row input {
  flex: 0 0 auto;
  inline-size: 1.125rem;
  block-size: 1.125rem;
  margin: 0;
}

.aggregations-selection-row label {
  display: flex;
  flex: 1;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-4);
}

.aggregations-method-status {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

@media (pointer: coarse) {
  .aggregations-history > summary,
  .aggregations-advanced > summary,
  .aggregations-selection-row {
    min-block-size: 2.75rem;
  }
}
</style>
