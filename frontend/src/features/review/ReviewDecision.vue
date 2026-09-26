<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useSlots, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useDraftNavigation, useDraftRegistration } from '@/composables/useDraftNavigation'

import { useCreateAnnotation, type AnnotationTarget } from './useAnnotate'
import type { AnnotationHistory } from './useReviewData'
import { CANONICAL_LABELS, useVocabularyGloss, type CanonicalLabel } from './useVocabulary'
import VocabBadge from './VocabBadge.vue'

const props = withDefaults(
  defineProps<{
    item: AnnotationTarget & { machine_label?: CanonicalLabel | null }
    /** The freshly read chain; its `revision` is what a decision is written against. */
    history: AnnotationHistory | undefined
    historyRefreshing: boolean
    historyFailed?: boolean
    contextReady?: boolean
    canReview: boolean
  }>(),
  { contextReady: true },
)

const { t, n } = useI18n()
const gloss = useVocabularyGloss()
const create = useCreateAnnotation()
const draftNavigation = useDraftNavigation()
const hasResultsSlot = Boolean(useSlots().results)

// One choice among: confirm the machine label, correct to one of the four labels, or defer.
type Choice = '' | 'verify' | 'defer' | `correct:${CanonicalLabel}`
const choice = ref<Choice>('')
const comment = ref('')
const saved = ref('')
const conflict = ref(false)
let draftGeneration = 0

const conflictBox = ref<HTMLElement | null>(null)
const savedBox = ref<HTMLElement | null>(null)

// IDs can recur in other snapshots. A different person or evidence context starts a clean draft.
watch(
  [() => props.item.snapshot_id, () => props.item.tei_id, () => props.item.aggregated_result_id],
  () => {
    draftGeneration += 1
    choice.value = ''
    comment.value = ''
    saved.value = ''
    conflict.value = false
    create.reset()
  },
)

const machineLabel = computed(() => props.item.machine_label ?? null)
const ready = computed(
  () =>
    props.history !== undefined &&
    props.history.snapshot_id === props.item.snapshot_id &&
    props.history.tei_id === props.item.tei_id &&
    !props.historyRefreshing &&
    !props.historyFailed &&
    props.contextReady !== false,
)
// While a conflict is open the stale choice cannot be saved: the reviewer must first decide again
// (or discard), so somebody else's newer decision is never overwritten unseen.
const canSave = computed(
  () =>
    props.canReview &&
    ready.value &&
    choice.value !== '' &&
    !conflict.value &&
    !create.isPending.value,
)
const latest = computed(() => props.history?.annotations[0] ?? null)

function decoded(): {
  action: 'verify' | 'correct' | 'defer'
  label: CanonicalLabel | null
} | null {
  const value = choice.value
  if (value === 'verify')
    return machineLabel.value ? { action: 'verify', label: machineLabel.value } : null
  if (value === 'defer') return { action: 'defer', label: null }
  if (value.startsWith('correct:')) {
    return { action: 'correct', label: value.slice('correct:'.length) as CanonicalLabel }
  }
  return null
}

async function save(): Promise<void> {
  const decision = decoded()
  const revision = props.history?.revision
  if (!canSave.value || !decision || revision === undefined) return
  const generation = draftGeneration
  const submittedChoice = choice.value
  const submittedComment = comment.value
  const matchesSubmittedDraft = () =>
    choice.value === submittedChoice && comment.value === submittedComment
  saved.value = ''
  conflict.value = false
  try {
    const annotation = await create.mutateAsync({
      item: props.item,
      action: decision.action,
      label: decision.label,
      comment: submittedComment,
      expectedRevision: revision,
    })
    if (generation !== draftGeneration) return
    const revisionText = n(annotation.resulting_revision, 'integer')
    saved.value = annotation.label
      ? t('review.decision.savedWithLabel', {
          action: gloss.action(annotation.action),
          label: annotation.label,
          revision: revisionText,
        })
      : t('review.decision.saved', {
          action: gloss.action(annotation.action),
          revision: revisionText,
        })
    const draftUnchanged = matchesSubmittedDraft()
    if (draftUnchanged) {
      choice.value = ''
      comment.value = ''
    }
    await nextTick()
    if (generation === draftGeneration && draftUnchanged && !draftNavigation.isOpen.value) {
      savedBox.value?.focus()
    }
  } catch (error) {
    if (generation !== draftGeneration) return
    if (error instanceof ApiError && error.code === 'annotation_conflict') {
      // Nothing was written. The chain is being re-read; the reviewer decides again on that.
      conflict.value = true
      await nextTick()
      if (
        generation === draftGeneration &&
        matchesSubmittedDraft() &&
        !draftNavigation.isOpen.value
      ) {
        conflictBox.value?.focus()
      }
    }
  }
}

function decideAgain(): void {
  // The comment is kept, the choice is not: the decision was made against a state that is gone.
  choice.value = ''
  conflict.value = false
  create.reset()
}

function discard(): void {
  draftGeneration += 1
  choice.value = ''
  comment.value = ''
  conflict.value = false
  create.reset()
}

watch(
  () => props.canReview,
  (allowed) => {
    if (allowed) return
    discard()
    saved.value = ''
  },
  { flush: 'sync' },
)

useDraftRegistration(() => choice.value !== '' || comment.value !== '', discard)

const errorText = computed(() => {
  const error = create.error.value
  if (!create.isError.value || conflict.value || error === null) return ''
  if (error instanceof ApiError && error.code === 'forbidden')
    return t('review.decision.errors.forbidden')
  if (error instanceof ApiError && error.code === 'network_error')
    return t('review.decision.errors.network')
  return t('review.decision.errors.generic')
})

// Single-key shortcuts 1-4 choose the label to correct to (docs/25); Enter then saves. They stand
// down while text is being typed or a select is open, where digits mean something else.
function isTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true
  if (target instanceof HTMLInputElement) {
    return !['radio', 'checkbox', 'button', 'submit', 'reset'].includes(target.type)
  }
  return false
}

function onKeydown(event: KeyboardEvent): void {
  if (draftNavigation.isOpen.value) return
  if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return
  if (!props.canReview || !ready.value || isTextEntry(event.target)) return
  const index = ['1', '2', '3', '4'].indexOf(event.key)
  const label = CANONICAL_LABELS[index]
  if (index === -1 || !label) return
  event.preventDefault()
  choice.value = `correct:${label}`
  saved.value = ''
  // Enter then saves: the button is the next thing the keyboard is on.
  void nextTick(() => document.getElementById('decision-save')?.focus())
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  draftGeneration += 1
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <section
    class="decision"
    :class="{ 'decision--split': hasResultsSlot }"
    aria-labelledby="decision-heading"
  >
    <form v-if="canReview" class="decision-form" novalidate @submit.prevent="save">
      <div class="decision-controls">
        <h3 id="decision-heading" class="decision-heading">{{ t('review.decision.title') }}</h3>
        <div v-if="conflict" ref="conflictBox" class="decision-conflict" role="alert" tabindex="-1">
          <p class="decision-conflict-title">{{ t('review.decision.conflict.title') }}</p>
          <p>{{ t('review.decision.conflict.body') }}</p>
          <p v-if="latest" class="decision-conflict-latest">
            {{
              t('review.decision.conflict.latest', {
                action: latest.action,
                name: latest.reviewer_display_name,
              })
            }}
            <VocabBadge v-if="latest.label" :value="latest.label" kind="label" />
          </p>
          <div class="decision-conflict-actions">
            <AppButton class="decision-decide-again" type="button" @click="decideAgain">
              {{ t('review.decision.conflict.again') }}
            </AppButton>
            <AppButton class="decision-discard" type="button" variant="ghost" @click="discard">
              {{ t('review.decision.conflict.discard') }}
            </AppButton>
          </div>
        </div>

        <div class="decision-choice-layout">
          <fieldset class="decision-choices">
            <legend>{{ t('review.decision.choose') }}</legend>

            <div v-if="item.aggregated_result_id" class="choice choice--verify">
              <input
                id="decision-verify"
                v-model="choice"
                type="radio"
                name="decision"
                value="verify"
                :disabled="machineLabel === null"
              />
              <label for="decision-verify">
                {{ t('review.decision.verify') }}
                <VocabBadge v-if="machineLabel" :value="machineLabel" kind="label" />
                <span v-else class="decision-muted">{{ t('review.decision.noMachineLabel') }}</span>
              </label>
            </div>

            <div class="choice choice--defer">
              <input
                id="decision-defer"
                v-model="choice"
                type="radio"
                name="decision"
                value="defer"
              />
              <label for="decision-defer">{{ t('review.decision.defer') }}</label>
            </div>

            <div class="decision-correction">
              <p class="decision-subtitle">
                {{
                  item.aggregated_result_id
                    ? t('review.decision.correctTo')
                    : t('annotation.chooseLabel')
                }}
              </p>
              <div
                v-for="(label, index) in CANONICAL_LABELS"
                :key="label"
                class="choice choice--label"
              >
                <input
                  :id="`decision-correct-${label}`"
                  v-model="choice"
                  type="radio"
                  name="decision"
                  :value="`correct:${label}`"
                />
                <label :for="`decision-correct-${label}`">
                  <VocabBadge :value="label" kind="label" />
                  <span class="decision-key-announcement">{{
                    t('review.decision.key', { key: index + 1 })
                  }}</span>
                  <kbd class="decision-key" aria-hidden="true">{{ index + 1 }}</kbd>
                </label>
              </div>
            </div>
          </fieldset>

          <div class="decision-save-area">
            <AppButton id="decision-save" class="decision-save" type="submit" :disabled="!canSave">
              {{ create.isPending.value ? t('review.decision.saving') : t('review.decision.save') }}
            </AppButton>
            <p ref="savedBox" class="decision-saved" role="status" tabindex="-1">{{ saved }}</p>
          </div>
        </div>

        <p class="decision-muted">{{ t('review.decision.keyboardHint') }}</p>
        <AppFeedback
          v-if="errorText"
          class="decision-error"
          announcement="assertive"
          tone="critical"
          >{{ errorText }}</AppFeedback
        >
      </div>

      <slot name="results"></slot>

      <details class="decision-footer decision-comment-disclosure">
        <summary id="decision-comment-summary" class="decision-comment-summary">
          {{ t('review.decision.comment') }}
        </summary>
        <div class="decision-comment">
          <textarea
            id="decision-comment"
            v-model="comment"
            class="app-multiline-field"
            rows="2"
            aria-labelledby="decision-comment-summary"
          ></textarea>
        </div>
      </details>
    </form>

    <template v-else>
      <div class="decision-controls">
        <h3 id="decision-heading" class="decision-heading">{{ t('review.decision.title') }}</h3>
        <AppFeedback class="decision-muted">{{ t('review.decision.viewerNote') }}</AppFeedback>
      </div>
      <slot name="results"></slot>
    </template>
  </section>
</template>

<style scoped>
.decision {
  min-width: 0;
  container: review-decision / inline-size;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--page-gutter);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--surface-1);
}

.decision--split {
  gap: var(--space-4);
  padding: 0;
  border: 0;
  background: transparent;
}

.decision-heading {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.decision-form {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-3);
}

.decision--split .decision-form {
  gap: var(--space-4);
}

.decision-controls {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.decision--split .decision-controls,
.decision--split .decision-footer {
  padding: var(--page-gutter);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--surface-1);
}

.decision-choice-layout {
  width: 100%;
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: var(--space-3);
}

.decision-choices {
  width: 100%;
  margin: 0;
  padding: 0;
  border: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
  gap: var(--space-2);
}

.decision-choices legend {
  grid-column: 1 / -1;
  padding: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.decision-subtitle {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.decision-correction {
  min-width: 0;
  display: flex;
  grid-column: 1 / -1;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.decision-correction .decision-subtitle {
  flex: 0 1 auto;
}

.choice {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: var(--space-2);
  min-block-size: var(--control-min-size);
}

.choice--label {
  flex: 0 1 auto;
}

.choice label {
  min-width: 0;
  overflow-wrap: anywhere;
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  min-block-size: var(--control-min-size);
}

.decision-save-area {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
}

.decision-key-announcement {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.decision-key {
  padding: 0 var(--space-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  color: var(--text-secondary);
  font: var(--font-size-small) var(--font-mono, ui-monospace, monospace);
}

.decision-comment {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-small);
}

.decision-footer {
  min-width: 0;
}

.decision-comment-disclosure > summary {
  padding-block: var(--space-2);
  cursor: pointer;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.decision-comment-disclosure > summary::marker {
  color: var(--accent);
}

.decision-comment-disclosure > summary:hover {
  background: var(--surface-1);
}

.decision-comment-disclosure[open] > summary {
  border-bottom: 1px solid var(--grid);
}

.decision-comment-disclosure .decision-comment {
  padding-top: var(--space-2);
}

.decision-muted {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.decision-saved {
  margin: 0;
  color: var(--good);
}

.decision-conflict {
  width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--critical);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.decision-conflict p {
  margin: 0 0 var(--space-2);
}

.decision-conflict-title {
  color: var(--critical-text);
  font-weight: var(--weight-semibold);
}

.decision-conflict-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
@container review-decision (max-width: 32rem) {
  .decision-choice-layout {
    grid-template-columns: minmax(0, 1fr);
    align-items: stretch;
  }

  .decision-choices {
    grid-template-columns: minmax(0, 1fr);
  }

  .decision-save-area {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
  }
}
</style>
