<script setup lang="ts">
// Guided mode's replacement for "Statistik & Methoden" (D27 follow-up, decided 2026-10-14): an
// evaluation is a separate, manually-created benchmark comparison (NewEvaluationForm.vue) that
// rarely exists right after Step 2 — linking straight to "the" evaluation of the current run would
// often have nothing to show. A gender-ratio chart from the project's working aggregation (ADR-0035)
// is simpler, always available the moment generation completes, and answers the question a guided
// user actually has. The full Auswertungen feature (benchmarks, confusion matrices, kappa) remains
// exactly as it is in the advanced presentation; this view does not replace or remove any of it.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import VocabBadge from '@/components/domain/VocabBadge.vue'
import { useAggregation } from '@/composables/useAggregations'
import { useProject } from '@/composables/useProjects'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useReviewSummary } from '@/composables/useReviewData'
import { CANONICAL_LABELS } from '@/composables/useVocabulary'

import { reviewProgress } from './projectStats'

const { t, n } = useI18n()
const { session, isSignedIn, retrySession } = useRequireSession()
const projectId = useRouteParam('projectId')

const project = useProject(projectId, isSignedIn)
const workingAggregationId = computed(
  () => project.data.value?.working_aggregation_execution_id ?? null,
)
const workingAggregationEnabled = computed(() => workingAggregationId.value !== null)
const aggregation = useAggregation(
  computed(() => workingAggregationId.value ?? ''),
  workingAggregationEnabled,
)
const isCompleted = computed(() => aggregation.data.value?.status === 'completed')
const summary = useReviewSummary(
  computed(() => workingAggregationId.value ?? ''),
  isCompleted,
)

const progress = computed(() => {
  const groups = summary.data.value?.groups
  return groups ? reviewProgress(groups) : null
})
const total = computed(() => summary.data.value?.result_count ?? 0)

const LABEL_COLORS: Record<string, string> = {
  male: 'var(--male)',
  female: 'var(--female)',
  institution: 'var(--institution)',
  unknown: 'var(--unknown)',
}
const UNLABELLED_COLOR = 'var(--muted)'

interface Segment {
  key: string
  label: string | null
  count: number
  percentage: number
  color: string
  /** Where this segment's arc starts, in the same 0-100 units as `percentage` (CSS-Tricks donut technique). */
  offset: number
}

// A donut built from stacked circles (circumference ~100 at r=15.9155), each segment a dash of its
// own percentage, rotated into place by an accumulating offset. Decorative only — the legend below
// carries the actual numbers for assistive technology.
const segments = computed<Segment[]>(() => {
  const current = progress.value
  if (!current || total.value === 0) return []
  const entries: { key: string; label: string | null; count: number; color: string }[] = [
    ...CANONICAL_LABELS.map((label) => ({
      key: label,
      label,
      count: current.labels[label],
      color: LABEL_COLORS[label] ?? UNLABELLED_COLOR,
    })),
    { key: 'unlabelled', label: null, count: current.unlabelled, color: UNLABELLED_COLOR },
  ]
  let cumulative = 0
  const result: Segment[] = []
  for (const entry of entries) {
    if (entry.count === 0) continue
    const percentage = (entry.count / total.value) * 100
    result.push({ ...entry, percentage, offset: 25 - cumulative })
    cumulative += percentage
  }
  return result
})
</script>

<template>
  <main class="gender-statistics app-page-frame">
    <RouterLink
      class="gender-statistics-back"
      :to="{ name: 'projectGenderTagging', params: { projectId } }"
    >
      {{ t('genderTagging.review.goToOverview') }}
    </RouterLink>
    <header class="app-page-heading">
      <h1 class="app-page-heading__title">{{ t('genderStatistics.title') }}</h1>
    </header>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      announcement="polite"
    >
      {{ t('projects.loading') }}
    </AppFeedback>
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="app-card"
      tone="critical"
      announcement="assertive"
    >
      {{ t('projects.sessionLoadError') }}
      <template #actions>
        <AppButton variant="ghost" @click="retrySession">{{ t('projects.retry') }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <AppFeedback v-if="project.isPending.value" class="app-card" announcement="polite">
        {{ t('projects.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="project.isError.value"
        class="app-card"
        tone="critical"
        announcement="assertive"
      >
        {{ t('data.projectLoadError') }}
        <template #actions>
          <AppButton variant="ghost" @click="project.refetch()">{{ t('projects.retry') }}</AppButton>
        </template>
      </AppFeedback>
      <AppFeedback v-else-if="workingAggregationId === null" class="app-card">
        {{ t('genderStatistics.noWorkingAggregation') }}
        <template #actions>
          <AppButton variant="ghost" :to="{ name: 'projectGenderTagging', params: { projectId } }">
            {{ t('nav.genderTagging') }}
          </AppButton>
        </template>
      </AppFeedback>
      <AppFeedback v-else-if="aggregation.isPending.value" class="app-card" announcement="polite">
        {{ t('projects.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="aggregation.isError.value"
        class="app-card"
        tone="critical"
        announcement="assertive"
      >
        {{ t('projects.overview.review.aggregationLoadError') }}
        <template #actions>
          <AppButton variant="ghost" @click="aggregation.refetch()">{{
            t('projects.retry')
          }}</AppButton>
        </template>
      </AppFeedback>
      <AppFeedback v-else-if="!isCompleted" class="app-card">
        {{
          t('genderStatistics.notCompleted', { status: aggregation.data.value?.status ?? '' })
        }}
      </AppFeedback>
      <AppFeedback v-else-if="summary.isPending.value" class="app-card" announcement="polite">
        {{ t('projects.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="summary.isError.value"
        class="app-card"
        tone="critical"
        announcement="assertive"
      >
        {{ t('projects.overview.review.summaryLoadError') }}
        <template #actions>
          <AppButton variant="ghost" @click="summary.refetch()">{{ t('projects.retry') }}</AppButton>
        </template>
      </AppFeedback>
      <AppFeedback v-else-if="total === 0" class="app-card">
        {{ t('genderStatistics.noPeople') }}
      </AppFeedback>
      <div v-else class="gender-statistics-card app-card">
        <p class="gender-statistics-total">
          {{ t('genderStatistics.total', { count: n(total, 'integer') }) }}
        </p>
        <div class="gender-statistics-chart">
          <svg viewBox="0 0 42 42" class="gender-statistics-donut" aria-hidden="true">
            <circle
              v-for="segment in segments"
              :key="segment.key"
              cx="21"
              cy="21"
              r="15.91549430918954"
              fill="transparent"
              :stroke="segment.color"
              stroke-width="6"
              :stroke-dasharray="`${segment.percentage} ${100 - segment.percentage}`"
              :stroke-dashoffset="segment.offset"
            />
          </svg>
          <dl class="gender-statistics-legend">
            <div v-for="segment in segments" :key="segment.key" class="gender-statistics-entry">
              <dt>
                <VocabBadge v-if="segment.label" kind="label" :value="segment.label" />
                <span v-else class="gender-statistics-unlabelled">{{
                  t('projects.overview.review.noLabel')
                }}</span>
              </dt>
              <dd>
                {{ n(segment.count, 'integer') }}
                <span class="gender-statistics-percentage">{{
                  `(${n(segment.percentage / 100, 'percent')})`
                }}</span>
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </template>
  </main>
</template>

<style scoped>
.gender-statistics-back {
  display: inline-block;
  margin-block-end: var(--space-4);
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.gender-statistics-total {
  margin: 0 0 var(--space-5);
  color: var(--text-secondary);
}

.gender-statistics-chart {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-6) var(--space-8);
}

.gender-statistics-donut {
  flex-shrink: 0;
  inline-size: 11rem;
  block-size: 11rem;
  transform: rotate(0deg);
}

.gender-statistics-legend {
  display: grid;
  flex: 1 1 16rem;
  gap: var(--space-3);
  margin: 0;
  min-inline-size: 0;
}

.gender-statistics-entry {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2) var(--space-4);
}

.gender-statistics-entry dd {
  margin: 0;
  font-weight: var(--weight-semibold);
  white-space: nowrap;
}

.gender-statistics-percentage {
  color: var(--text-secondary);
  font-weight: var(--weight-regular);
}

.gender-statistics-unlabelled {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
</style>
