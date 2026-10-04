<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppSelectField from '@/components/base/AppSelectField.vue'
import { useDraftNavigation, useDraftRegistration } from '@/composables/useDraftNavigation'

import { reviewItemName } from '@/components/domain/reviewItemName'
import { useBulkDecision, type BulkResult, type BulkSpec } from './useBulkDecision'
import { CANONICAL_LABELS, useVocabularyGloss } from '@/composables/useVocabulary'
import type { components } from '@/api/schema'

type ReviewItem = components['schemas']['ReviewItem']
type CanonicalLabel = components['schemas']['CanonicalLabel']

const props = withDefaults(
  defineProps<{
    /** The selected people, in list order. */
    items: readonly ReviewItem[]
    /** How many people the list holds right now, for "select all". */
    loadedCount: number
    contextReady?: boolean
  }>(),
  { contextReady: true },
)
const emit = defineEmits<{
  toggleAll: [checked: boolean]
  clear: []
  /** People whose decision was saved: they leave the selection, the rest stays for another try. */
  finished: [saved: string[]]
}>()

const { t, n } = useI18n()
const gloss = useVocabularyGloss()
const bulk = useBulkDecision()
const navigation = useDraftNavigation()
let generation = 0

type Choice = '' | 'verify' | 'defer' | `correct:${CanonicalLabel}`
const choice = ref<Choice>('')
const comment = ref('')
const step = ref<'choose' | 'confirm'>('choose')
// The people as they were when the run started: the report must stay readable after the selection moves.
const names = ref<Record<string, string>>({})

function discardDraft(): void {
  generation += 1
  // A submitted annotation remains an append-only write. Stop prevents the next person only;
  // the request already in flight is allowed to finish and retains its server outcome.
  if (bulk.phase.value === 'running') bulk.stop()
  else bulk.reset()
  choice.value = ''
  comment.value = ''
  step.value = 'choose'
  names.value = {}
}

useDraftRegistration(
  () => choice.value !== '' || comment.value !== '' || bulk.phase.value === 'running',
  discardDraft,
)
onScopeDispose(() => {
  generation += 1
  bulk.stop()
})

const count = computed(() => props.items.length)
const allSelected = computed(() => props.loadedCount > 0 && count.value === props.loadedCount)
const someSelected = computed(() => count.value > 0 && !allSelected.value)

const spec = computed<BulkSpec | null>(() => {
  const value = choice.value
  if (value === 'verify') return { action: 'verify', label: null, comment: comment.value }
  if (value === 'defer') return { action: 'defer', label: null, comment: comment.value }
  if (value.startsWith('correct:')) {
    return {
      action: 'correct',
      label: value.slice('correct:'.length) as CanonicalLabel,
      comment: comment.value,
    }
  }
  return null
})

// Confirming machine labels can only cover people the machine gave one.
const withoutMachineLabel = computed(() =>
  choice.value === 'verify' ? props.items.filter((item) => !item.machine_label).length : 0,
)

const confirmBox = ref<HTMLElement | null>(null)
const reportBox = ref<HTMLElement | null>(null)

const actionText = computed(() => {
  const value = choice.value
  if (value === 'verify') return t('review.bulk.actions.verify')
  if (value === 'defer') return t('review.bulk.actions.defer')
  if (value.startsWith('correct:')) {
    return t('review.bulk.actions.correct', { label: value.slice('correct:'.length) })
  }
  return ''
})

async function toConfirm(): Promise<void> {
  if (props.contextReady === false || !spec.value || count.value === 0) return
  const requestGeneration = generation
  step.value = 'confirm'
  await nextTick()
  if (requestGeneration === generation && !navigation.isOpen.value) confirmBox.value?.focus()
}

async function apply(): Promise<void> {
  const current = spec.value
  if (props.contextReady === false || !current || bulk.phase.value === 'running') return
  const requestGeneration = generation
  names.value = Object.fromEntries(props.items.map((item) => [item.tei_id, reviewItemName(item)]))
  step.value = 'choose'
  const results = await bulk.run(props.items, current)
  if (requestGeneration !== generation) return
  emit(
    'finished',
    results.filter((r) => r.outcome.kind === 'saved').map((r) => r.teiId),
  )
  choice.value = ''
  comment.value = ''
  await nextTick()
  if (requestGeneration === generation && !navigation.isOpen.value) reportBox.value?.focus()
}

function closeReport(): void {
  bulk.reset()
}

// A run's report belongs to that run: choosing something new starts from a clean bar.
// (Clearing the choice after a run must not close that run's own report, only a new choice does.)
watch(choice, (value) => {
  if (value !== '' && bulk.phase.value === 'done') bulk.reset()
})

const counts = computed(() => {
  const tally = { saved: 0, conflict: 0, skipped: 0, other: 0 }
  for (const result of bulk.results.value) {
    const kind = result.outcome.kind
    if (kind === 'saved') tally.saved += 1
    else if (kind === 'conflict') tally.conflict += 1
    else if (kind === 'skipped') tally.skipped += 1
    else tally.other += 1
  }
  return tally
})

function outcomeText(result: BulkResult): string {
  const outcome = result.outcome
  switch (outcome.kind) {
    case 'saved':
      return t('review.bulk.outcome.saved', { revision: n(outcome.revision, 'integer') })
    case 'conflict':
      return outcome.currentRevision === null
        ? t('review.bulk.outcome.conflict')
        : t('review.bulk.outcome.conflictAt', { revision: n(outcome.currentRevision, 'integer') })
    case 'skipped':
      return t('review.bulk.outcome.skipped')
    case 'forbidden':
      return t('review.bulk.outcome.forbidden')
    case 'failed':
      return t('review.bulk.outcome.failed')
    case 'notAttempted':
      return t('review.bulk.outcome.notAttempted')
  }
}

const PREVIEW_LIMIT = 6
const preview = computed(() => props.items.slice(0, PREVIEW_LIMIT).map(reviewItemName))
</script>

<template>
  <section class="bulk" :aria-label="t('review.bulk.label')">
    <div class="bulk-select">
      <input
        id="bulk-all"
        type="checkbox"
        :checked="allSelected"
        :indeterminate="someSelected"
        :disabled="loadedCount === 0 || bulk.phase.value === 'running'"
        @change="emit('toggleAll', ($event.target as HTMLInputElement).checked)"
      />
      <label for="bulk-all">{{
        t('review.bulk.selectAll', { count: n(loadedCount, 'integer') })
      }}</label>
      <span class="bulk-count" role="status">{{
        count > 0 ? t('review.bulk.selected', { count: n(count, 'integer') }) : ''
      }}</span>
      <AppButton
        v-if="count > 0 && bulk.phase.value !== 'running'"
        class="bulk-clear"
        type="button"
        variant="text"
        @click="emit('clear')"
      >
        {{ t('review.bulk.clear') }}
      </AppButton>
    </div>

    <form
      v-if="count > 0 && bulk.phase.value !== 'running' && step === 'choose'"
      class="bulk-form"
      novalidate
      @submit.prevent="toConfirm"
    >
      <AppSelectField
        id="bulk-action"
        v-model="choice"
        class="bulk-field"
        :label="t('review.bulk.action')"
      >
        <option value="">{{ t('review.bulk.choose') }}</option>
        <option value="verify">{{ t('review.bulk.actions.verify') }}</option>
        <option v-for="label in CANONICAL_LABELS" :key="label" :value="`correct:${label}`">
          {{ t('review.bulk.actions.correct', { label }) }}
          {{ gloss.label(label) ? `(${gloss.label(label)})` : '' }}
        </option>
        <option value="defer">{{ t('review.bulk.actions.defer') }}</option>
      </AppSelectField>
      <div class="bulk-field">
        <label for="bulk-comment">{{ t('review.bulk.comment') }}</label>
        <textarea
          id="bulk-comment"
          v-model="comment"
          class="app-multiline-field"
          rows="2"
        ></textarea>
      </div>
      <AppButton class="bulk-review" type="submit" :disabled="!spec || contextReady === false">
        {{ t('review.bulk.review') }}
      </AppButton>
    </form>

    <div
      v-if="step === 'confirm' && bulk.phase.value !== 'running'"
      ref="confirmBox"
      class="bulk-confirm"
      role="group"
      tabindex="-1"
      :aria-label="t('review.bulk.confirmTitle')"
    >
      <p class="bulk-confirm-title">
        {{ t('review.bulk.confirm', { action: actionText, count: n(count, 'integer') }) }}
      </p>
      <p v-if="withoutMachineLabel > 0" class="bulk-note">
        {{ t('review.bulk.willSkip', { count: n(withoutMachineLabel, 'integer') }) }}
      </p>
      <p class="bulk-note">
        {{ preview.join('; ')
        }}<template v-if="count > preview.length">
          {{ t('review.bulk.andMore', { count: n(count - preview.length, 'integer') }) }}</template
        >
      </p>
      <p class="bulk-note">{{ t('review.bulk.appendOnly') }}</p>
      <div class="bulk-actions">
        <AppButton
          class="bulk-apply"
          type="button"
          :disabled="contextReady === false"
          @click="apply"
        >
          {{ t('review.bulk.apply') }}
        </AppButton>
        <AppButton class="bulk-back" type="button" variant="ghost" @click="step = 'choose'">
          {{ t('review.bulk.back') }}
        </AppButton>
      </div>
    </div>

    <AppFeedback v-if="bulk.phase.value === 'running'" class="bulk-progress" announcement="polite">
      {{
        t('review.bulk.progress', {
          done: n(bulk.done.value, 'integer'),
          total: n(bulk.total.value, 'integer'),
        })
      }}
      <template #actions>
        <AppButton
          class="bulk-stop"
          type="button"
          variant="ghost"
          :disabled="bulk.stopRequested.value"
          @click="bulk.stop()"
        >
          {{ bulk.stopRequested.value ? t('review.bulk.stopping') : t('review.bulk.stop') }}
        </AppButton>
      </template>
    </AppFeedback>

    <div v-if="bulk.phase.value === 'done'" ref="reportBox" class="bulk-report" tabindex="-1">
      <AppFeedback class="bulk-report-title" announcement="polite">
        {{
          t('review.bulk.summary', {
            saved: n(counts.saved, 'integer'),
            total: n(bulk.results.value.length, 'integer'),
          })
        }}
      </AppFeedback>
      <p v-if="counts.conflict + counts.skipped + counts.other > 0" class="bulk-note">
        {{ t('review.bulk.notSaved') }}
      </p>
      <ul class="bulk-report-list">
        <li
          v-for="result in bulk.results.value"
          :key="result.teiId"
          class="bulk-report-item"
          :class="`bulk-report-item--${result.outcome.kind}`"
        >
          <span class="bulk-report-name">{{ names[result.teiId] ?? result.teiId }}</span>
          <span class="bulk-report-outcome">{{ outcomeText(result) }}</span>
        </li>
      </ul>
      <AppButton class="bulk-close" type="button" variant="ghost" @click="closeReport">
        {{ t('review.bulk.close') }}
      </AppButton>
    </div>
  </section>
</template>

<style scoped>
.bulk {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--grid);
}

.bulk-select {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-small);
}

.bulk-count {
  color: var(--text-secondary);
}

.bulk-form,
.bulk-confirm,
.bulk-report {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
}

.bulk-field {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-small);
  --field-label-color: var(--text-primary);
  --field-control-width: 100%;
}

.bulk-confirm,
.bulk-report {
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--surface-1);
}

.bulk-confirm-title,
.bulk-report-title {
  margin: 0;
  font-weight: var(--weight-semibold);
}

.bulk-note {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.bulk-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.bulk-report-list {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.bulk-report-item {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  border-bottom: 1px solid var(--grid);
  font-size: var(--font-size-small);
}

.bulk-report-item--saved .bulk-report-outcome {
  color: var(--good);
}

.bulk-report-item--conflict .bulk-report-outcome,
.bulk-report-item--forbidden .bulk-report-outcome,
.bulk-report-item--failed .bulk-report-outcome {
  color: var(--critical-text);
}

.bulk-report-name {
  font-weight: var(--weight-semibold);
}
</style>
