<script setup lang="ts">
import { PhArrowDown, PhArrowUp } from '@phosphor-icons/vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'

import {
  useAnnotationHistory,
  usePersonRecord,
  useResultPredictions,
  type ResultMethodPrediction,
  type ReviewItem,
} from './useReviewData'
import {
  CANONICAL_LABELS,
  useVocabularyGloss,
  type CanonicalLabel,
  type CertaintyTier,
} from './useVocabulary'
import PersonRecordDetails from './PersonRecordDetails.vue'
import ReviewDecision from './ReviewDecision.vue'
import { reviewItemName } from './reviewItemName'
import VocabBadge from './VocabBadge.vue'

const props = withDefaults(
  defineProps<{
    item: ReviewItem
    canReview: boolean
    contextReady?: boolean
    canPrevious?: boolean
    canNext?: boolean
    navigationBusy?: boolean
    navigationFocusRequest?: number
    navigationFocusTarget?: 'previous' | 'next' | null
    navigationFocusPerson?: string | null
  }>(),
  {
    contextReady: true,
    canPrevious: false,
    canNext: false,
    navigationBusy: false,
    navigationFocusRequest: 0,
    navigationFocusTarget: null,
    navigationFocusPerson: null,
  },
)

const emit = defineEmits<{ previous: []; next: []; navigationFocusRestored: [] }>()

const navigation = ref<HTMLElement | null>(null)
const { t, d, n } = useI18n()
const gloss = useVocabularyGloss()

const aggregationId = computed(() => props.item.aggregation_execution_id)
const resultId = computed(() => props.item.aggregated_result_id)
const snapshotId = computed(() => props.item.snapshot_id)
const teiId = computed(() => props.item.tei_id)

const predictions = useResultPredictions(aggregationId, resultId)
const history = useAnnotationHistory(snapshotId, teiId)
const person = usePersonRecord(snapshotId, teiId)

const toneOf = (tier: CertaintyTier): 'contested' | 'low' | 'thin' | 'neutral' => {
  if (tier === 'contested') return 'contested'
  if (tier === 'low') return 'low'
  if (tier === 'single' || tier === 'uncertain') return 'thin'
  return 'neutral'
}

const displayName = computed(() => reviewItemName(props.item))

function onNavigationKeydown(event: KeyboardEvent): void {
  if (event.key === 'ArrowUp' && props.canPrevious) {
    event.preventDefault()
    emit('previous')
  } else if (event.key === 'ArrowDown' && props.canNext) {
    event.preventDefault()
    emit('next')
  }
}

async function focusNavigation(): Promise<void> {
  await nextTick()
  const preferredId =
    props.navigationFocusTarget === 'previous' ? '#detail-previous' : '#detail-next'
  const preferred = navigation.value?.querySelector<HTMLButtonElement>(
    `${preferredId}:not(:disabled)`,
  )
  const fallback = navigation.value?.querySelector<HTMLButtonElement>('button:not(:disabled)')
  const target = preferred ?? fallback
  target?.focus()
  if (target) emit('navigationFocusRestored')
}

onMounted(() => {
  if (props.navigationFocusRequest > 0 && props.navigationFocusPerson === props.item.tei_id) {
    void focusNavigation()
  }
})

watch(
  () => props.navigationFocusRequest,
  (request, previousRequest) => {
    if (
      request === 0 ||
      request === previousRequest ||
      props.navigationFocusPerson !== props.item.tei_id
    )
      return
    void focusNavigation()
  },
)

interface MethodPredictionGroup {
  label: CanonicalLabel | null
  entries: ResultMethodPrediction[]
}

const METHOD_GROUP_ORDER: readonly (CanonicalLabel | null)[] = [...CANONICAL_LABELS, null]
const groupedPredictions = computed<MethodPredictionGroup[]>(() => {
  const entriesByLabel = new Map<CanonicalLabel | null, ResultMethodPrediction[]>()
  for (const entry of predictions.data.value ?? []) {
    const label = entry.prediction?.label ?? null
    const entries = entriesByLabel.get(label)
    if (entries) entries.push(entry)
    else entriesByLabel.set(label, [entry])
  }
  return METHOD_GROUP_ORDER.flatMap((label) => {
    const entries = entriesByLabel.get(label)
    return entries ? [{ label, entries }] : []
  })
})

function methodGroupLabel(group: MethodPredictionGroup): string {
  const label = group.label
    ? [group.label, gloss.label(group.label)].filter(Boolean).join(' ')
    : t('review.detail.methods.unassigned')
  return t('review.detail.methods.groupSummary', {
    count: n(group.entries.length, 'integer'),
    label,
  })
}
</script>

<template>
  <article class="detail" :aria-labelledby="`detail-name-${item.tei_id}`">
    <header class="detail-title-row">
      <h2 :id="`detail-name-${item.tei_id}`" class="detail-name">
        {{ displayName }} <span class="detail-tei">{{ item.tei_id }}</span>
      </h2>
      <nav
        ref="navigation"
        class="detail-navigation"
        :aria-label="t('review.detail.navigation.label')"
        :aria-busy="navigationBusy ? 'true' : undefined"
      >
        <AppButton
          id="detail-previous"
          class="detail-navigation-button"
          type="button"
          variant="ghost"
          :disabled="!canPrevious"
          :aria-label="t('review.detail.navigation.previous')"
          :title="t('review.detail.navigation.previous')"
          aria-keyshortcuts="ArrowUp"
          @keydown="onNavigationKeydown"
          @click="emit('previous')"
        >
          <PhArrowUp :size="16" aria-hidden="true" />
        </AppButton>
        <AppButton
          id="detail-next"
          class="detail-navigation-button"
          type="button"
          variant="ghost"
          :disabled="!canNext"
          :aria-label="t('review.detail.navigation.next')"
          :title="t('review.detail.navigation.next')"
          aria-keyshortcuts="ArrowDown"
          @keydown="onNavigationKeydown"
          @click="emit('next')"
        >
          <PhArrowDown :size="16" aria-hidden="true" />
        </AppButton>
      </nav>
    </header>

    <ReviewDecision
      :item="item"
      :history="history.data.value"
      :history-refreshing="history.isFetching.value"
      :history-failed="history.isError.value"
      :context-ready="contextReady"
      :can-review="canReview"
    >
      <template #results>
        <div class="detail-overview">
          <section class="detail-card" aria-labelledby="detail-summary-heading">
            <h3 id="detail-summary-heading" class="detail-heading">
              {{ t('review.detail.summaryTitle') }}
            </h3>
            <dl class="detail-facts app-facts">
              <div class="detail-fact app-fact">
                <dt>{{ t('review.detail.certainty') }}</dt>
                <dd>
                  <VocabBadge
                    :value="item.certainty_tier"
                    kind="tier"
                    :tone="toneOf(item.certainty_tier)"
                  />
                </dd>
              </div>
              <div class="detail-fact app-fact">
                <dt>{{ t('review.detail.agreement') }}</dt>
                <dd>
                  <VocabBadge :value="item.agreement_tier" />
                </dd>
              </div>
              <div class="detail-fact app-fact">
                <dt>{{ t('review.detail.outcome') }}</dt>
                <dd>
                  <VocabBadge :value="item.aggregation_outcome" />
                </dd>
              </div>
              <div class="detail-fact app-fact">
                <dt>{{ t('review.detail.machineLabel') }}</dt>
                <dd>
                  <VocabBadge :value="item.machine_label" kind="label" />
                </dd>
              </div>
              <div class="detail-fact app-fact">
                <dt>{{ t('review.detail.finalLabel') }}</dt>
                <dd>
                  <VocabBadge :value="item.final_label" kind="label" />
                </dd>
              </div>
              <div class="detail-fact app-fact">
                <dt>{{ t('review.detail.state') }}</dt>
                <dd>
                  <VocabBadge :value="item.workflow_state" />
                  <span class="detail-revision">{{
                    t('review.detail.revision', { revision: n(item.review_revision, 'integer') })
                  }}</span>
                </dd>
              </div>
            </dl>

            <p v-if="item.override_source" class="detail-authority">
              <strong>{{ t('review.detail.authorityTitle') }}</strong>
              {{
                t('review.detail.authorityBody', { source: gloss.override(item.override_source) })
              }}
            </p>
            <p v-if="item.has_authority_conflict" class="detail-authority">
              <strong>{{ t('review.detail.conflictTitle') }}</strong>
              {{ t('review.detail.conflictBody') }}
            </p>
            <p v-if="item.has_prediction_error" class="detail-authority">
              <strong>{{ t('review.detail.errorTitle') }}</strong>
              {{ t('review.detail.errorBody') }}
            </p>
          </section>

          <section class="detail-section detail-card" aria-labelledby="detail-person-heading">
            <h3 id="detail-person-heading" class="detail-heading">
              {{ t('review.detail.person.title') }}
            </h3>
            <p v-if="person.isPending.value" role="status">{{ t('review.loading') }}</p>
            <p v-else-if="person.isError.value" role="alert" class="detail-error">
              {{ t('review.detail.person.loadError') }}
            </p>
            <PersonRecordDetails v-else-if="person.data.value" :record="person.data.value" />
          </section>
        </div>

        <section class="detail-section" aria-labelledby="detail-methods-heading">
          <h3 id="detail-methods-heading" class="detail-heading">
            {{ t('review.detail.methods.title') }}
          </h3>
          <p v-if="predictions.isPending.value" role="status">{{ t('review.loading') }}</p>
          <div v-else-if="predictions.isError.value" class="detail-load-error">
            <p role="alert">{{ t('review.detail.methods.loadError') }}</p>
            <AppButton type="button" @click="() => predictions.refetch()">{{
              t('review.retry')
            }}</AppButton>
          </div>
          <template v-else-if="predictions.data.value">
            <div class="detail-method-groups">
              <details
                v-for="group in groupedPredictions"
                :key="group.label ?? 'unassigned'"
                class="detail-method-group"
              >
                <summary :aria-label="methodGroupLabel(group)">
                  <span class="detail-method-group-summary" aria-hidden="true">
                    <span class="detail-method-group-count">
                      {{
                        t('review.detail.methods.groupCount', {
                          count: n(group.entries.length, 'integer'),
                        })
                      }}
                    </span>
                    <VocabBadge v-if="group.label" :value="group.label" kind="label" />
                    <span v-else>{{ t('review.detail.methods.unassigned') }}</span>
                  </span>
                </summary>
                <AppScrollRegion
                  :label="t('layout.tableRegion', { label: methodGroupLabel(group) })"
                >
                  <table class="detail-table">
                    <thead>
                      <tr>
                        <th scope="col">{{ t('review.detail.methods.method') }}</th>
                        <th scope="col">{{ t('review.detail.methods.label') }}</th>
                        <th scope="col">{{ t('review.detail.methods.status') }}</th>
                        <th scope="col">{{ t('review.detail.methods.confidence') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="entry in group.entries"
                        :key="entry.method_execution_id"
                        class="detail-method-row"
                      >
                        <th scope="row">{{ entry.method_name }}</th>
                        <template v-if="entry.prediction">
                          <td>
                            <VocabBadge :value="entry.prediction.label" kind="label" />
                            <span v-if="entry.prediction.raw_label" class="detail-raw">{{
                              t('review.detail.methods.raw', { raw: entry.prediction.raw_label })
                            }}</span>
                          </td>
                          <td>
                            <span
                              class="detail-status"
                              :class="`detail-status--${entry.prediction.status}`"
                              >{{ entry.prediction.status }}</span
                            >
                            <span class="detail-gloss">{{
                              gloss.prediction(entry.prediction.status)
                            }}</span>
                          </td>
                          <td>
                            <template v-if="entry.prediction.method_confidence != null">
                              {{ n(entry.prediction.method_confidence, 'confidence') }}
                            </template>
                            <span v-else class="detail-muted">{{ t('review.none') }}</span>
                          </td>
                        </template>
                        <td v-else colspan="3" class="detail-muted">
                          {{ t('review.detail.methods.noPrediction') }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </AppScrollRegion>
              </details>
            </div>
          </template>
        </section>
      </template>
    </ReviewDecision>
    <section class="detail-section" aria-labelledby="detail-history-heading">
      <details class="detail-history-disclosure">
        <summary>
          <h3 id="detail-history-heading" class="detail-heading">
            {{ t('review.detail.history.title') }}
          </h3>
        </summary>
        <div class="detail-history-content">
          <p v-if="history.isPending.value" role="status">{{ t('review.loading') }}</p>
          <div v-else-if="history.isError.value" class="detail-load-error">
            <p role="alert">{{ t('review.detail.history.loadError') }}</p>
            <AppButton type="button" @click="() => history.refetch()">{{
              t('review.retry')
            }}</AppButton>
          </div>
          <template v-else-if="history.data.value">
            <p v-if="history.data.value.annotations.length === 0" class="detail-muted">
              {{ t('review.detail.history.empty') }}
            </p>
            <template v-else>
              <p class="detail-note">
                {{
                  t('review.detail.history.revision', {
                    revision: n(history.data.value.revision, 'integer'),
                  })
                }}
              </p>
              <ol class="detail-history">
                <li
                  v-for="(entry, index) in history.data.value.annotations"
                  :key="entry.id"
                  class="detail-history-entry"
                  :class="{ 'detail-history-entry--current': index === 0 }"
                >
                  <p class="detail-history-head">
                    <span class="detail-revision-no">{{
                      t('review.detail.history.entry', {
                        revision: n(entry.resulting_revision, 'integer'),
                      })
                    }}</span>
                    <span class="detail-token">{{ entry.action }}</span>
                    <VocabBadge v-if="entry.label" :value="entry.label" kind="label" />
                    <span v-if="index === 0" class="detail-current">{{
                      t('review.detail.history.current')
                    }}</span>
                  </p>
                  <p class="detail-history-who">
                    <span>{{
                      t('review.detail.history.by', {
                        name: entry.reviewer_display_name,
                        when: d(new Date(entry.created_at), 'timestamp'),
                      })
                    }}</span>
                    <span v-if="entry.supersedes_annotation_id" class="detail-gloss">{{
                      t('review.detail.history.replaces', {
                        revision: n(entry.resulting_revision - 1, 'integer'),
                      })
                    }}</span>
                  </p>
                  <p v-if="entry.comment" class="detail-comment">{{ entry.comment }}</p>
                </li>
              </ol>
            </template>
          </template>
        </div>
      </details>
    </section>
  </article>
</template>

<style scoped>
.detail {
  min-width: 0;
  overflow-wrap: anywhere;
  container: review-detail / inline-size;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.detail-overview {
  display: grid;
  gap: var(--space-3);
}

.detail-card {
  min-width: 0;
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--surface-1);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

@container review-detail (min-width: 32rem) {
  .detail-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: stretch;
  }
}

.detail-title-row {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.detail-navigation {
  display: flex;
  flex: none;
  gap: var(--space-1);
}

.detail-navigation-button {
  padding: var(--space-2);
}

.detail-navigation-button :deep(svg) {
  flex: none;
}

.detail-name {
  min-width: 0;
  margin: 0;
  font-size: var(--font-size-title);
}

.detail-tei {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: normal;
}

.detail-facts {
  display: grid;
  gap: var(--space-2);
  margin: 0;
}

.detail-fact {
  align-items: baseline;
}

.detail-fact dt {
  color: var(--text-secondary);
}

.detail-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.detail-revision {
  margin-left: var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

/* A thin full border marks evidence that changes how the whole item should be read. */
.detail-authority {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--accent);
  border-radius: var(--radius-control);
  background: var(--surface-1);
}

.detail-section {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.detail-heading {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.detail-table {
  width: 100%;
  min-width: 30rem;
  border-collapse: collapse;
  font-size: var(--font-size-small);
}

.detail-table th,
.detail-table td {
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--grid);
  text-align: left;
  vertical-align: baseline;
}

.detail-table thead th {
  color: var(--text-secondary);
  font-weight: normal;
}

.detail-method-groups {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  gap: var(--space-2);
}

.detail-method-group {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--grid);
  border-radius: var(--radius-card);
}

@container review-detail (min-width: 28rem) {
  .detail-method-groups {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail-method-group[open] {
    grid-column: 1 / -1;
  }
}

@container review-detail (min-width: 48rem) {
  .detail-method-groups {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.detail-method-group > summary {
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  font-size: var(--font-size-small);
  font-weight: var(--weight-semibold);
}

.detail-method-group > summary::marker {
  color: var(--accent);
}

.detail-method-group > summary:hover {
  background: var(--surface-1);
}

.detail-method-group[open] > summary {
  border-bottom: 1px solid var(--grid);
}

.detail-method-group-summary {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  margin-inline-start: var(--space-1);
}

.detail-method-group-count {
  font-variant-numeric: tabular-nums;
}

.detail-table tbody th {
  font-weight: var(--weight-semibold);
}

.detail-raw,
.detail-gloss {
  margin-left: var(--space-2);
  color: var(--text-secondary);
}

.detail-status {
  font-family: var(--font-mono, ui-monospace, monospace);
}

.detail-status--error {
  color: var(--critical-text);
}

.detail-muted,
.detail-note {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.detail-error,
.detail-load-error p {
  margin: 0;
  color: var(--critical-text);
}

.detail-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
}

.detail-history-disclosure {
  min-width: 0;
  border: 1px solid var(--grid);
  border-radius: var(--radius-card);
}
.detail-history-disclosure > summary {
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
}
.detail-history-disclosure > summary::marker {
  color: var(--accent);
}
.detail-history-disclosure > summary:hover {
  background: var(--surface-1);
}
.detail-history-disclosure > summary .detail-heading {
  display: inline;
}
.detail-history-disclosure[open] > summary {
  border-bottom: 1px solid var(--grid);
}
.detail-history-content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3) var(--space-3);
}
.detail-history {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0 0 0 var(--space-4);
  border-left: 2px solid var(--grid);
  list-style: none;
}

.detail-history-entry--current .detail-token {
  color: var(--accent);
}

.detail-revision-no {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.detail-current {
  color: var(--accent);
  font-size: var(--font-size-small);
}

.detail-history-who {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.detail-history-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  margin: 0;
}

.detail-token {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: var(--weight-semibold);
}

.detail-comment {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
}
</style>
