<script setup lang="ts">
import { PhArrowRight } from '@phosphor-icons/vue'
import { computed, toRef } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppProgress from '@/components/base/AppProgress.vue'
import { useAggregation } from '@/composables/useAggregations'

import VocabBadge from '@/components/domain/VocabBadge.vue'
import { useReviewSummary } from '@/composables/useReviewData'
import { QUEUES, queueCounts, type QueueId } from '@/components/domain/reviewQueues'
import { CANONICAL_LABELS, WORKFLOW_STATES } from '@/composables/useVocabulary'
import ProjectOverviewSection from './ProjectOverviewSection.vue'
import ProjectStat from './ProjectStat.vue'
import ProjectStatList from './ProjectStatList.vue'
import { reviewProgress } from './projectStats'

const props = defineProps<{
  projectId: string
  /** The project's working aggregation (ADR-0035), or null when none has been chosen. */
  aggregationId: string | null
}>()
const { t, d, n } = useI18n()

const aggregationId = toRef(props, 'aggregationId')
const aggregation = useAggregation(
  computed(() => aggregationId.value ?? ''),
  computed(() => aggregationId.value !== null),
)
const isCompleted = computed(() => aggregation.data.value?.status === 'completed')
// Only a completed aggregation has results to summarize.
const summary = useReviewSummary(
  computed(() => aggregationId.value ?? ''),
  isCompleted,
)

const progress = computed(() => {
  const groups = summary.data.value?.groups
  return groups ? reviewProgress(groups) : null
})
const queues = computed(() => {
  const groups = summary.data.value?.groups
  return groups ? queueCounts(groups) : null
})
const total = computed(() => summary.data.value?.result_count ?? 0)
const reviewedShare = computed(() =>
  progress.value && total.value > 0 ? (progress.value.reviewed / total.value) * 100 : null,
)

function queueTitle(queue: QueueId): string {
  switch (queue) {
    case 'contested':
      return t('review.queue.contested.title')
    case 'thin':
      return t('review.queue.thin.title')
    case 'all':
      return t('review.queue.all.title')
  }
}

function queueHint(queue: QueueId): string {
  switch (queue) {
    case 'contested':
      return t('review.queue.contested.hint')
    case 'thin':
      return t('review.queue.thin.hint')
    case 'all':
      return t('review.queue.all.hint')
  }
}

// The whole-register queue is the plain traversal, not an evidence bucket: it is the progress bar's
// total already.
const evidenceQueues = QUEUES.filter((queue) => queue !== 'all')
</script>

<template>
  <ProjectOverviewSection :title="t('projects.overview.review.title')">
    <p v-if="aggregationId === null" class="review-note">
      {{ t('projects.overview.review.noWorkingAggregation') }}
    </p>
    <p v-else-if="aggregation.isPending.value" role="status">{{ t('projects.loading') }}</p>
    <AppFeedback v-else-if="aggregation.isError.value" tone="critical" announcement="polite">
      <p>{{ t('projects.overview.review.aggregationLoadError') }}</p>
      <template #actions>
        <AppButton type="button" variant="ghost" @click="() => aggregation.refetch()">{{
          t('projects.retry')
        }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="aggregation.data.value">
      <p v-if="!isCompleted" class="review-note">
        {{ t('projects.overview.review.notCompleted', { status: aggregation.data.value.status }) }}
      </p>
      <p v-else-if="summary.isPending.value" role="status">{{ t('projects.loading') }}</p>
      <AppFeedback v-else-if="summary.isError.value" tone="critical" announcement="polite">
        <p>{{ t('projects.overview.review.summaryLoadError') }}</p>
        <template #actions>
          <AppButton type="button" variant="ghost" @click="() => summary.refetch()">{{
            t('projects.retry')
          }}</AppButton>
        </template>
      </AppFeedback>
      <p v-else-if="total === 0" class="review-note">
        {{ t('projects.overview.review.noPeople') }}
      </p>
      <div v-else-if="progress && queues" class="review-body">
        <div class="review-block">
          <p class="review-progress-caption">
            {{
              t('projects.overview.review.progress', {
                reviewed: n(progress.reviewed, 'integer'),
                total: n(total, 'integer'),
              })
            }}
          </p>
          <AppProgress
            :percentage="reviewedShare"
            :label="t('projects.overview.review.progressLabel')"
          />
          <ProjectStatList>
            <ProjectStat v-for="state in WORKFLOW_STATES" :key="state">
              <template #label>
                <VocabBadge kind="state" :value="state" />
              </template>
              {{ n(progress[state], 'integer') }}
              <template v-if="state === 'reviewed' && progress.reviewed > 0" #detail>
                {{
                  t('projects.overview.review.decisionSplit', {
                    verified: n(progress.verified, 'integer'),
                    corrected: n(progress.corrected, 'integer'),
                  })
                }}
              </template>
            </ProjectStat>
          </ProjectStatList>
        </div>

        <div class="review-block">
          <h3 class="review-block-title">{{ t('projects.overview.review.queuesTitle') }}</h3>
          <ProjectStatList>
            <ProjectStat v-for="queue in evidenceQueues" :key="queue">
              <template #label>{{ queueTitle(queue) }}</template>
              {{
                t('review.queue.count', {
                  open: n(queues[queue].open, 'integer'),
                  total: n(queues[queue].total, 'integer'),
                })
              }}
              <template #detail>{{ queueHint(queue) }}</template>
            </ProjectStat>
          </ProjectStatList>
        </div>

        <div class="review-block">
          <h3 class="review-block-title">{{ t('projects.overview.review.labelsTitle') }}</h3>
          <p class="review-note">{{ t('projects.overview.review.labelsHint') }}</p>
          <ProjectStatList>
            <ProjectStat v-for="label in CANONICAL_LABELS" :key="label">
              <template #label>
                <VocabBadge kind="label" :value="label" />
              </template>
              {{ n(progress.labels[label], 'integer') }}
            </ProjectStat>
            <ProjectStat v-if="progress.unlabelled > 0">
              <template #label>{{ t('projects.overview.review.noLabel') }}</template>
              {{ n(progress.unlabelled, 'integer') }}
            </ProjectStat>
          </ProjectStatList>
        </div>

        <p v-if="summary.data.value?.last_annotated_at" class="review-note">
          {{
            t('projects.overview.review.lastActivity', {
              when: d(new Date(summary.data.value.last_annotated_at), 'timestamp'),
            })
          }}
        </p>
        <div class="review-actions">
          <AppButton
            :to="{
              name: 'review',
              params: {
                projectId,
                runId: aggregation.data.value.run_id,
                aggregationId: aggregation.data.value.id,
              },
            }"
            variant="ghost"
          >
            {{ t('projects.overview.review.openReview') }}
            <PhArrowRight :size="18" aria-hidden="true" />
          </AppButton>
          <AppButton
            :to="{
              name: 'people',
              params: {
                projectId,
                runId: aggregation.data.value.run_id,
                aggregationId: aggregation.data.value.id,
              },
            }"
            variant="ghost"
          >
            {{ t('projects.overview.review.browsePeople') }}
          </AppButton>
        </div>
      </div>
    </template>
  </ProjectOverviewSection>
</template>

<style scoped>
.review-body {
  display: grid;
  gap: var(--space-6);
}
.review-block {
  display: grid;
  gap: var(--space-3);
  min-inline-size: 0;
}
.review-block-title {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-body);
}
.review-progress-caption,
.review-note,
p[role='status'] {
  margin: 0;
}
.review-note {
  color: var(--text-secondary);
}
.review-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}
.review-actions svg {
  flex-shrink: 0;
}
</style>
