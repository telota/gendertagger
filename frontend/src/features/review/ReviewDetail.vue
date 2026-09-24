<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'

import {
  useAnnotationHistory,
  usePersonRecord,
  useResultPredictions,
  type ReviewItem,
} from './useReviewData'
import { useVocabularyGloss, type CertaintyTier } from './useVocabulary'
import ReviewDecision from './ReviewDecision.vue'
import VocabBadge from './VocabBadge.vue'

const props = defineProps<{ item: ReviewItem; canReview: boolean }>()

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

const displayName = computed(() => {
  const forenames = (props.item.forenames ?? []).join(' ')
  if (props.item.surname && forenames) return `${props.item.surname}, ${forenames}`
  return props.item.surname ?? (forenames || props.item.tei_id)
})

const personFacts = computed(() => {
  const record = person.data.value
  if (!record) return []
  const facts: { key: string; label: string; value: string }[] = []
  if (record.birth)
    facts.push({ key: 'birth', label: t('review.detail.person.birth'), value: record.birth })
  if (record.death)
    facts.push({ key: 'death', label: t('review.detail.person.death'), value: record.death })
  if (record.gnd_id)
    facts.push({ key: 'gnd', label: t('review.detail.person.gnd'), value: record.gnd_id })
  if (record.alt_names && record.alt_names.length > 0) {
    facts.push({
      key: 'altNames',
      label: t('review.detail.person.altNames'),
      value: record.alt_names.join('; '),
    })
  }
  if (record.note)
    facts.push({ key: 'note', label: t('review.detail.person.note'), value: record.note })
  return facts
})
</script>

<template>
  <article class="detail" :aria-labelledby="`detail-name-${item.tei_id}`">
    <h2 :id="`detail-name-${item.tei_id}`" class="detail-name">
      {{ displayName }} <span class="detail-tei">{{ item.tei_id }}</span>
    </h2>

    <dl class="detail-facts">
      <div class="detail-fact">
        <dt>{{ t('review.detail.certainty') }}</dt>
        <dd>
          <VocabBadge
            :value="item.certainty_tier"
            :gloss="gloss.certainty(item.certainty_tier)"
            kind="tier"
            :tone="toneOf(item.certainty_tier)"
          />
        </dd>
      </div>
      <div class="detail-fact">
        <dt>{{ t('review.detail.agreement') }}</dt>
        <dd>
          <VocabBadge :value="item.agreement_tier" :gloss="gloss.agreement(item.agreement_tier)" />
        </dd>
      </div>
      <div class="detail-fact">
        <dt>{{ t('review.detail.outcome') }}</dt>
        <dd>
          <VocabBadge
            :value="item.aggregation_outcome"
            :gloss="gloss.outcome(item.aggregation_outcome)"
          />
        </dd>
      </div>
      <div class="detail-fact">
        <dt>{{ t('review.detail.machineLabel') }}</dt>
        <dd>
          <VocabBadge
            :value="item.machine_label"
            :gloss="item.machine_label ? gloss.label(item.machine_label) : ''"
            kind="label"
          />
        </dd>
      </div>
      <div class="detail-fact">
        <dt>{{ t('review.detail.finalLabel') }}</dt>
        <dd>
          <VocabBadge
            :value="item.final_label"
            :gloss="item.final_label ? gloss.label(item.final_label) : ''"
            kind="label"
          />
        </dd>
      </div>
      <div class="detail-fact">
        <dt>{{ t('review.detail.state') }}</dt>
        <dd>
          <VocabBadge :value="item.workflow_state" :gloss="gloss.workflow(item.workflow_state)" />
          <span class="detail-revision">{{
            t('review.detail.revision', { revision: n(item.review_revision, 'integer') })
          }}</span>
        </dd>
      </div>
    </dl>

    <p v-if="item.override_source" class="detail-authority">
      <strong>{{ t('review.detail.authorityTitle') }}</strong>
      {{ t('review.detail.authorityBody', { source: gloss.override(item.override_source) }) }}
    </p>
    <p v-if="item.has_authority_conflict" class="detail-authority">
      <strong>{{ t('review.detail.conflictTitle') }}</strong>
      {{ t('review.detail.conflictBody') }}
    </p>
    <p v-if="item.has_prediction_error" class="detail-authority">
      <strong>{{ t('review.detail.errorTitle') }}</strong>
      {{ t('review.detail.errorBody') }}
    </p>

    <section class="detail-section" aria-labelledby="detail-person-heading">
      <h3 id="detail-person-heading" class="detail-heading">
        {{ t('review.detail.person.title') }}
      </h3>
      <p v-if="person.isPending.value" role="status">{{ t('review.loading') }}</p>
      <p v-else-if="person.isError.value" role="alert" class="detail-error">
        {{ t('review.detail.person.loadError') }}
      </p>
      <dl v-else-if="personFacts.length > 0" class="detail-facts detail-facts--person">
        <div v-for="fact in personFacts" :key="fact.key" class="detail-fact">
          <dt>{{ fact.label }}</dt>
          <dd>{{ fact.value }}</dd>
        </div>
      </dl>
      <p v-else class="detail-muted">{{ t('review.detail.person.empty') }}</p>
    </section>

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
            <tr v-for="entry in predictions.data.value" :key="entry.method_execution_id">
              <th scope="row">{{ entry.method_name }}</th>
              <template v-if="entry.prediction">
                <td>
                  <VocabBadge
                    :value="entry.prediction.label"
                    :gloss="entry.prediction.label ? gloss.label(entry.prediction.label) : ''"
                    kind="label"
                  />
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
                  <span class="detail-gloss">{{ gloss.prediction(entry.prediction.status) }}</span>
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
        <p class="detail-note">{{ t('review.detail.methods.confidenceNote') }}</p>
      </template>
    </section>

    <ReviewDecision
      :item="item"
      :history="history.data.value"
      :history-refreshing="history.isFetching.value"
      :can-review="canReview"
    />

    <section class="detail-section" aria-labelledby="detail-history-heading">
      <h3 id="detail-history-heading" class="detail-heading">
        {{ t('review.detail.history.title') }}
      </h3>
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
                <span class="detail-token">{{ entry.action }}</span>
                <VocabBadge v-if="entry.label" :value="entry.label" kind="label" />
                <span class="detail-gloss">{{
                  t('review.detail.history.by', {
                    name: entry.reviewer_display_name,
                    when: d(new Date(entry.created_at), 'timestamp'),
                  })
                }}</span>
              </p>
              <p v-if="entry.comment" class="detail-comment">{{ entry.comment }}</p>
            </li>
          </ol>
        </template>
      </template>
    </section>
  </article>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.detail-name {
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
  display: grid;
  grid-template-columns: 9rem 1fr;
  gap: var(--space-3);
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

/* The one field that changes how the whole item should be read gets its own marked block. */
.detail-authority {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-left: 4px solid var(--accent);
  border-radius: 0 var(--radius-card) var(--radius-card) 0;
  background: var(--surface-1);
}

.detail-section {
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
  color: var(--critical);
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
  color: var(--critical);
}

.detail-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
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
