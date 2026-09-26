<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'
import {
  AGGREGATABLE_EXECUTION_STATUSES,
  useAggregationList,
} from '@/features/runs/useAggregations'
import { useRunExecutions } from '@/features/runs/useRunDetail'

import { useCreateEvaluation, type EvaluationExecution } from './useEvaluations'

const props = defineProps<{
  projectId: string
  runId: string
  /** Newest first. An earlier evaluation shows what selection the server accepted before. */
  earlier: readonly EvaluationExecution[]
}>()

const { t } = useI18n()
const router = useRouter()
const heading = ref<HTMLElement>()

function focusHeading(): void {
  heading.value?.focus()
}

defineExpose({ focusHeading })

const runId = computed(() => props.runId)
const executions = useRunExecutions(runId)
const aggregations = useAggregationList(runId)
const create = useCreateEvaluation()

const eligible = computed(() =>
  (executions.data.value ?? []).filter((execution) =>
    AGGREGATABLE_EXECUTION_STATUSES.has(execution.status),
  ),
)
const completedAggregations = computed(() =>
  (aggregations.data.value?.pages.flatMap((page) => page.items) ?? []).filter(
    (aggregation) => aggregation.status === 'completed',
  ),
)

// The definition prescribes exactly which methods it needs, and the contract does not say which. The
// best starting point is what the server accepted last time; with no earlier evaluation, everything.
const previous = computed(() => props.earlier[0] ?? null)
const preselected = computed(
  () => new Set(previous.value?.method_execution_ids ?? eligible.value.map((e) => e.id)),
)
const chosen = ref<Record<string, boolean>>({})
const isChosen = (id: string): boolean => chosen.value[id] ?? preselected.value.has(id)
const selectedIds = computed(() => eligible.value.filter((e) => isChosen(e.id)).map((e) => e.id))

const picked = ref<string | null>(null)
const defaultAggregation = computed(
  () => previous.value?.aggregation_execution_id ?? completedAggregations.value[0]?.id ?? '',
)
const aggregationChoice = computed({
  get: () => picked.value ?? defaultAggregation.value,
  set: (value: string) => {
    picked.value = value
  },
})

const draftFingerprint = computed(() =>
  JSON.stringify([[...selectedIds.value].sort(), aggregationChoice.value]),
)
const acceptedDraft = ref<string | null>(null)
let draftGeneration = 0
function resetDraft(): void {
  draftGeneration += 1
  create.reset()
  chosen.value = {}
  picked.value = null
  acceptedDraft.value = null
}
useDraftRegistration(
  () =>
    create.isPending.value ||
    (draftFingerprint.value !== acceptedDraft.value &&
      (eligible.value.some(({ id }) => isChosen(id) !== preselected.value.has(id)) ||
        (picked.value !== null && picked.value !== defaultAggregation.value))),
  resetDraft,
)
watch(() => props.runId, resetDraft)
onScopeDispose(() => {
  draftGeneration += 1
})

const canSubmit = computed(() => selectedIds.value.length > 0 && !create.isPending.value)

const errorText = computed(() => {
  const error = create.error.value
  if (!create.isError.value || error === null) return ''
  if (error instanceof ApiError && error.code === 'resource_conflict') {
    return t('evaluation.new.errors.notEvaluatable')
  }
  if (error instanceof ApiError && error.code === 'network_error') {
    return t('evaluation.new.errors.network')
  }
  return t('evaluation.new.errors.generic')
})

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  const owner = draftGeneration
  const submittedDraft = draftFingerprint.value
  try {
    const evaluation = await create.mutateAsync({
      run_id: props.runId,
      definition: 'gnd_benchmark_v1',
      method_execution_ids: selectedIds.value,
      ...(aggregationChoice.value ? { aggregation_execution_id: aggregationChoice.value } : {}),
    })
    if (owner !== draftGeneration) return
    acceptedDraft.value = submittedDraft
    // A started evaluation is watched, so the operator lands on it rather than back on the list.
    void router.push({
      name: 'evaluationDetail',
      params: { projectId: props.projectId, runId: props.runId, evaluationId: evaluation.id },
    })
  } catch {
    // create.isError/.error already reflect this; the form stays filled to be corrected.
  }
}
</script>

<template>
  <form
    class="new-evaluation"
    novalidate
    aria-labelledby="new-evaluation-heading"
    @submit.prevent="submit"
  >
    <h2 id="new-evaluation-heading" ref="heading" class="new-evaluation-title" tabindex="-1">
      {{ t('evaluation.new.title') }}
    </h2>
    <p class="new-evaluation-hint">{{ t('evaluation.new.hint') }}</p>

    <p v-if="executions.isPending.value" role="status">{{ t('runs.loading') }}</p>
    <div v-else-if="executions.isError.value" class="new-evaluation-load-error">
      <p role="alert">{{ t('evaluation.new.executionsLoadError') }}</p>
      <AppButton type="button" @click="() => executions.refetch()">{{ t('runs.retry') }}</AppButton>
    </div>
    <template v-else>
      <p class="new-evaluation-definition">
        {{ t('evaluation.new.definition', { definition: 'gnd_benchmark_v1' }) }}
      </p>

      <details class="new-evaluation-options">
        <summary>
          {{ t('evaluation.new.options', { count: selectedIds.length }) }}
        </summary>
        <div class="new-evaluation-options-content">
          <fieldset class="new-evaluation-methods">
            <legend>{{ t('evaluation.new.methods') }}</legend>
            <p class="new-evaluation-hint">
              {{ previous ? t('evaluation.new.fromEarlier') : t('evaluation.new.fromAll') }}
            </p>
            <div v-for="execution in eligible" :key="execution.id" class="new-evaluation-method">
              <input
                :id="`evaluate-${execution.id}`"
                type="checkbox"
                :checked="isChosen(execution.id)"
                @change="chosen[execution.id] = ($event.target as HTMLInputElement).checked"
              />
              <label :for="`evaluate-${execution.id}`">{{ execution.method_name }}</label>
            </div>
          </fieldset>

          <div class="new-evaluation-field">
            <label for="evaluate-aggregation">{{ t('evaluation.new.aggregation') }}</label>
            <select id="evaluate-aggregation" v-model="aggregationChoice">
              <option value="">{{ t('evaluation.new.noAggregation') }}</option>
              <option
                v-for="aggregation in completedAggregations"
                :key="aggregation.id"
                :value="aggregation.id"
              >
                {{
                  t('evaluation.new.aggregationOption', {
                    strategy: aggregation.strategy ?? '',
                    hash: aggregation.config_sha256.slice(0, 8),
                  })
                }}
              </option>
            </select>
            <p class="new-evaluation-hint">{{ t('evaluation.new.aggregationHint') }}</p>
          </div>
        </div>
      </details>

      <p v-if="errorText" role="alert" class="new-evaluation-error">{{ errorText }}</p>
      <div class="app-form-actions">
        <AppButton class="new-evaluation-submit" type="submit" :disabled="!canSubmit">
          {{ create.isPending.value ? t('evaluation.new.submitting') : t('evaluation.new.submit') }}
        </AppButton>
      </div>
    </template>
  </form>
</template>

<style scoped>
.new-evaluation {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.new-evaluation-title {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.new-evaluation-title:focus {
  outline: none;
}

.new-evaluation-hint,
.new-evaluation-definition {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.new-evaluation-methods {
  margin: 0;
  padding: 0;
  border: 0;
}

.new-evaluation-options {
  inline-size: 100%;
  border-block: 1px solid var(--border);
}

.new-evaluation-options > summary {
  display: flex;
  min-block-size: var(--control-min-size);
  align-items: center;
  padding-block: var(--space-2);
  font-weight: var(--weight-semibold);
  cursor: pointer;
}

.new-evaluation-options-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding-block: var(--space-2) var(--space-4);
}

.new-evaluation-methods legend {
  padding: 0;
  font-weight: var(--weight-semibold);
}

.new-evaluation-method {
  display: flex;
  min-block-size: var(--control-min-size);
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.new-evaluation-method input {
  flex: none;
}

.new-evaluation-method label {
  display: flex;
  min-width: 0;
  min-block-size: var(--control-min-size);
  flex: 1;
  align-items: center;
  overflow-wrap: anywhere;
  cursor: pointer;
}

.new-evaluation-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-small);
}

.new-evaluation-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
}

.new-evaluation-load-error p,
.new-evaluation-error {
  margin: 0;
  color: var(--critical-text);
}
</style>
