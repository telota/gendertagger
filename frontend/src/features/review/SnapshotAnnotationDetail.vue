<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import PersonRecordDetails from './PersonRecordDetails.vue'
import ReviewDecision from './ReviewDecision.vue'
import VocabBadge from './VocabBadge.vue'
import { reviewItemName } from './reviewItemName'
import { useAnnotationHistory, usePersonRecord } from './useReviewData'
import type { SnapshotAnnotationItem } from './useSnapshotAnnotations'

const props = withDefaults(
  defineProps<{
    item: SnapshotAnnotationItem
    canReview: boolean
    contextReady?: boolean
  }>(),
  { contextReady: true },
)
const { t, d, n } = useI18n()
const snapshotId = computed(() => props.item.snapshot_id)
const teiId = computed(() => props.item.tei_id)
const person = usePersonRecord(snapshotId, teiId)
const history = useAnnotationHistory(snapshotId, teiId)
const currentHistory = computed(() =>
  history.data.value?.snapshot_id === snapshotId.value && history.data.value.tei_id === teiId.value
    ? history.data.value
    : undefined,
)
</script>

<template>
  <article class="annotation-detail" aria-labelledby="annotation-person-heading">
    <header class="annotation-title-row">
      <h2 id="annotation-person-heading">
        {{ reviewItemName(item) }} <code>{{ item.tei_id }}</code>
      </h2>
    </header>

    <ReviewDecision
      :item="item"
      :history="currentHistory"
      :history-refreshing="history.isFetching.value"
      :history-failed="history.isError.value"
      :context-ready="contextReady"
      :can-review="canReview"
    >
      <template #results>
        <div class="annotation-overview">
          <section class="annotation-card" aria-labelledby="annotation-summary-heading">
            <h3 id="annotation-summary-heading" class="annotation-section-heading">
              {{ t('review.detail.summaryTitle') }}
            </h3>
            <dl class="annotation-current app-facts">
              <div class="app-fact">
                <dt>{{ t('review.detail.state') }}</dt>
                <dd>
                  <VocabBadge :value="item.workflow_state" kind="state" />
                  <span class="annotation-revision">{{
                    t('review.detail.revision', {
                      revision: n(item.review_revision, 'integer'),
                    })
                  }}</span>
                </dd>
              </div>
              <div class="app-fact">
                <dt>{{ t('annotation.humanLabel') }}</dt>
                <dd>
                  <VocabBadge v-if="item.human_label" :value="item.human_label" kind="label" />
                  <span v-else>{{ t('annotation.noDecision') }}</span>
                </dd>
              </div>
            </dl>
          </section>

          <section class="annotation-card" aria-labelledby="annotation-source-heading">
            <h3 id="annotation-source-heading" class="annotation-section-heading">
              {{ t('review.detail.person.title') }}
            </h3>
            <AppFeedback v-if="person.isPending.value" announcement="polite">{{
              t('review.loading')
            }}</AppFeedback>
            <AppFeedback v-else-if="person.isError.value" tone="critical" announcement="assertive">
              {{ t('review.detail.person.loadError') }}
              <template #actions>
                <AppButton variant="ghost" @click="person.refetch()">
                  {{ t('review.retry') }}
                </AppButton>
              </template>
            </AppFeedback>
            <PersonRecordDetails
              v-else-if="
                person.data.value?.tei_id === item.tei_id &&
                person.data.value?.dataset_snapshot_id === item.snapshot_id
              "
              :record="person.data.value"
            />
          </section>
        </div>
      </template>
    </ReviewDecision>

    <section class="annotation-section" aria-labelledby="annotation-history-heading">
      <details class="annotation-history-disclosure">
        <summary>
          <h3 id="annotation-history-heading" class="annotation-section-heading">
            {{ t('review.detail.history.title') }}
          </h3>
        </summary>
        <div class="annotation-history-content">
          <AppFeedback v-if="history.isPending.value" announcement="polite">{{
            t('review.loading')
          }}</AppFeedback>
          <AppFeedback v-else-if="history.isError.value" tone="critical" announcement="assertive">
            {{ t('review.detail.history.loadError') }}
            <template #actions>
              <AppButton variant="ghost" @click="history.refetch()">
                {{ t('review.retry') }}
              </AppButton>
            </template>
          </AppFeedback>
          <template v-else-if="currentHistory">
            <p v-if="!currentHistory.annotations.length" class="annotation-muted">
              {{ t('review.detail.history.empty') }}
            </p>
            <template v-else>
              <p class="annotation-muted">
                {{
                  t('review.detail.history.revision', {
                    revision: n(currentHistory.revision, 'integer'),
                  })
                }}
              </p>
              <ol class="annotation-history">
                <li
                  v-for="(entry, index) in currentHistory.annotations"
                  :key="entry.id"
                  :class="{ 'annotation-history-entry--current': index === 0 }"
                >
                  <p class="annotation-history-head">
                    <span class="annotation-revision-number">{{
                      t('review.detail.history.entry', {
                        revision: n(entry.resulting_revision, 'integer'),
                      })
                    }}</span>
                    <span class="annotation-token">{{ entry.action }}</span>
                    <VocabBadge v-if="entry.label" :value="entry.label" kind="label" />
                    <span v-if="index === 0" class="annotation-current-marker">{{
                      t('review.detail.history.current')
                    }}</span>
                  </p>
                  <p class="annotation-history-who">
                    <span>{{
                      t('review.detail.history.by', {
                        name: entry.reviewer_display_name,
                        when: d(new Date(entry.created_at), 'timestamp'),
                      })
                    }}</span>
                    <span v-if="entry.supersedes_annotation_id">{{
                      t('review.detail.history.replaces', {
                        revision: n(entry.resulting_revision - 1, 'integer'),
                      })
                    }}</span>
                  </p>
                  <p v-if="entry.comment" class="annotation-comment">{{ entry.comment }}</p>
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
.annotation-detail {
  container: annotation-detail / inline-size;
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: var(--space-4);
  overflow-wrap: anywhere;
}

.annotation-title-row h2 {
  min-width: 0;
  margin: 0;
  font-size: var(--font-size-title);
}

.annotation-title-row code {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: normal;
}

.annotation-overview {
  display: grid;
  gap: var(--space-3);
}

@container annotation-detail (min-width: 32rem) {
  .annotation-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: stretch;
  }
}

.annotation-card {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--surface-1);
}

.annotation-section {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: var(--space-2);
}

.annotation-section-heading {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.annotation-current {
  display: grid;
  gap: var(--space-2);
  margin: 0;
}

.annotation-current dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.annotation-revision {
  margin-inline-start: var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.annotation-history-disclosure {
  min-width: 0;
  border: 1px solid var(--grid);
  border-radius: var(--radius-card);
}

.annotation-history-disclosure > summary {
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
}

.annotation-history-disclosure > summary::marker {
  color: var(--accent);
}

.annotation-history-disclosure > summary:hover {
  background: var(--surface-1);
}

.annotation-history-disclosure > summary .annotation-section-heading {
  display: inline;
}

.annotation-history-disclosure[open] > summary {
  border-bottom: 1px solid var(--grid);
}

.annotation-history-content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3) var(--space-3);
}

.annotation-muted {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.annotation-history {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0 0 0 var(--space-4);
  border-inline-start: 2px solid var(--grid);
  list-style: none;
}

.annotation-history-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  margin: 0;
}

.annotation-history-entry--current .annotation-token,
.annotation-current-marker {
  color: var(--accent);
}

.annotation-revision-number,
.annotation-current-marker {
  font-size: var(--font-size-small);
}

.annotation-revision-number,
.annotation-history-who {
  color: var(--text-secondary);
}

.annotation-token {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: var(--weight-semibold);
}

.annotation-history-who {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--font-size-small);
}

.annotation-comment {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
}
</style>
