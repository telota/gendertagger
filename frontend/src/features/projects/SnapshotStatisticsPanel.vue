<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'

import { useSnapshotStatistics } from './useSnapshotData'

const props = defineProps<{ projectId: string; snapshotId: string }>()
const { t, n } = useI18n()
const query = useSnapshotStatistics(
  toRef(props, 'projectId'),
  toRef(props, 'snapshotId'),
  computed(() => true),
)
const statistics = computed(() => {
  const value = query.data.value
  return value?.dataset_snapshot_id === props.snapshotId ? value : null
})
const sourceGender = computed(() => statistics.value?.source_gender ?? null)
const distribution = computed(() => {
  const source = sourceGender.value
  if (!source) return []
  return [
    { key: 'male', label: t('data.statistics.gender.male'), count: source.male_count },
    { key: 'female', label: t('data.statistics.gender.female'), count: source.female_count },
    { key: 'unknown', label: t('data.statistics.gender.unknown'), count: source.unknown_count },
    {
      key: 'institution',
      label: t('data.statistics.gender.institution'),
      count: source.institution_count,
    },
    {
      key: 'other',
      label: t('data.statistics.gender.otherOrMultiple'),
      count: source.other_or_multiple_count,
    },
  ]
})

function progressMax(total: number): number {
  return Math.max(total, 1)
}

function percentage(count: number, total: number): string {
  return n(total === 0 ? 0 : count / total, {
    style: 'percent',
    maximumFractionDigits: 0,
  })
}

function countText(count: number, total: number): string {
  return t('data.statistics.countOfTotal', {
    count: n(count, 'integer'),
    total: n(total, 'integer'),
    percentage: percentage(count, total),
  })
}

function progressLabel(label: string, count: number, total: number): string {
  return t('data.statistics.progressLabel', {
    label,
    count: n(count, 'integer'),
    total: n(total, 'integer'),
  })
}
</script>

<template>
  <section class="snapshot-statistics app-card" aria-labelledby="snapshot-statistics-title">
    <header class="snapshot-statistics-header">
      <div>
        <h2 id="snapshot-statistics-title">{{ t('data.statistics.title') }}</h2>
        <p>{{ t('data.statistics.description') }}</p>
      </div>
      <p v-if="statistics" class="snapshot-statistics-total">
        {{
          t('data.statistics.totalPeople', { count: n(statistics.total_person_count, 'integer') })
        }}
      </p>
    </header>

    <AppFeedback v-if="query.isPending.value" announcement="polite">
      {{ t('data.statistics.loading') }}
    </AppFeedback>
    <AppFeedback
      v-else-if="query.isError.value || !statistics"
      announcement="polite"
      tone="critical"
    >
      {{ t('data.statistics.loadError') }}
      <template #actions>
        <AppButton
          type="button"
          variant="ghost"
          :disabled="query.isFetching.value"
          @click="query.refetch()"
        >
          {{ t('projects.retry') }}
        </AppButton>
      </template>
    </AppFeedback>

    <div v-else class="snapshot-statistics-body">
      <section class="snapshot-statistics-block" aria-labelledby="snapshot-coverage-title">
        <h3 id="snapshot-coverage-title">{{ t('data.statistics.coverageTitle') }}</h3>
        <ul class="snapshot-statistics-list">
          <li v-if="sourceGender" class="snapshot-statistic">
            <div class="snapshot-statistic-copy">
              <span class="snapshot-statistic-label">{{ t('data.statistics.sourceGender') }}</span>
              <span class="snapshot-statistic-value">
                {{ countText(sourceGender.with_element_count, statistics.total_person_count) }}
              </span>
            </div>
            <progress
              :aria-label="
                progressLabel(
                  t('data.statistics.sourceGender'),
                  sourceGender.with_element_count,
                  statistics.total_person_count,
                )
              "
              :max="progressMax(statistics.total_person_count)"
              :value="sourceGender.with_element_count"
            ></progress>
          </li>
          <li v-else class="snapshot-statistic snapshot-statistic--unavailable">
            <span class="snapshot-statistic-label">{{ t('data.statistics.sourceGender') }}</span>
            <span class="snapshot-statistic-value">{{ t('data.statistics.notCaptured') }}</span>
          </li>

          <li class="snapshot-statistic">
            <div class="snapshot-statistic-copy">
              <span class="snapshot-statistic-label">{{ t('data.statistics.gndReference') }}</span>
              <span class="snapshot-statistic-value">
                {{ countText(statistics.gnd.with_reference_count, statistics.total_person_count) }}
              </span>
            </div>
            <progress
              :aria-label="
                progressLabel(
                  t('data.statistics.gndReference'),
                  statistics.gnd.with_reference_count,
                  statistics.total_person_count,
                )
              "
              :max="progressMax(statistics.total_person_count)"
              :value="statistics.gnd.with_reference_count"
            ></progress>
          </li>

          <li v-if="sourceGender" class="snapshot-statistic">
            <div class="snapshot-statistic-copy">
              <span class="snapshot-statistic-label">{{
                t('data.statistics.gndAndSourceGender')
              }}</span>
              <span class="snapshot-statistic-value">
                {{
                  countText(
                    statistics.gnd.with_reference_and_source_gender_count ?? 0,
                    statistics.total_person_count,
                  )
                }}
              </span>
            </div>
            <progress
              :aria-label="
                progressLabel(
                  t('data.statistics.gndAndSourceGender'),
                  statistics.gnd.with_reference_and_source_gender_count ?? 0,
                  statistics.total_person_count,
                )
              "
              :max="progressMax(statistics.total_person_count)"
              :value="statistics.gnd.with_reference_and_source_gender_count ?? 0"
            ></progress>
          </li>
          <li v-else class="snapshot-statistic snapshot-statistic--unavailable">
            <span class="snapshot-statistic-label">{{
              t('data.statistics.gndAndSourceGender')
            }}</span>
            <span class="snapshot-statistic-value">{{ t('data.statistics.notCaptured') }}</span>
          </li>
        </ul>
      </section>

      <section class="snapshot-statistics-block" aria-labelledby="snapshot-gender-values-title">
        <h3 id="snapshot-gender-values-title">{{ t('data.statistics.genderTitle') }}</h3>
        <p v-if="sourceGender" class="snapshot-statistics-note">
          {{
            t('data.statistics.genderDescription', {
              count: n(sourceGender.with_element_count, 'integer'),
            })
          }}
        </p>
        <ul v-if="sourceGender" class="snapshot-statistics-list snapshot-statistics-distribution">
          <li
            v-for="item in distribution"
            :key="item.key"
            class="snapshot-statistic"
            :class="`snapshot-statistic--${item.key}`"
          >
            <div class="snapshot-statistic-copy">
              <span class="snapshot-statistic-label">{{ item.label }}</span>
              <span class="snapshot-statistic-value">{{ n(item.count, 'integer') }}</span>
            </div>
            <progress
              :aria-label="progressLabel(item.label, item.count, sourceGender.with_element_count)"
              :max="progressMax(sourceGender.with_element_count)"
              :value="item.count"
            ></progress>
          </li>
        </ul>
        <p v-else class="snapshot-statistics-note">{{ t('data.statistics.notCapturedDetail') }}</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.snapshot-statistics {
  margin-block-start: var(--space-6);
}

.snapshot-statistics-header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2) var(--space-6);
  margin-block-end: var(--space-5);
}

.snapshot-statistics h2,
.snapshot-statistics h3,
.snapshot-statistics p,
.snapshot-statistics ul {
  margin: 0;
}

.snapshot-statistics h2 {
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.snapshot-statistics-header > div > p,
.snapshot-statistics-note {
  margin-block-start: var(--space-1);
  color: var(--text-secondary);
}

.snapshot-statistics-total {
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  font-weight: var(--weight-semibold);
}

.snapshot-statistics-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-6);
}

.snapshot-statistics-block + .snapshot-statistics-block {
  padding-inline-start: var(--space-6);
  border-inline-start: 1px solid var(--border);
}

.snapshot-statistics h3 {
  font-size: var(--font-size-body);
  font-weight: var(--weight-semibold);
}

.snapshot-statistics-list {
  display: grid;
  gap: var(--space-4);
  margin-block-start: var(--space-3);
  padding: 0;
  list-style: none;
}

.snapshot-statistic {
  display: grid;
  gap: var(--space-2);
}

.snapshot-statistic-copy {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}

.snapshot-statistic-label {
  font-weight: var(--weight-semibold);
}

.snapshot-statistic-value {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-variant-numeric: tabular-nums;
  text-align: end;
}

.snapshot-statistic progress {
  inline-size: 100%;
  block-size: 0.5rem;
  border: 0;
  accent-color: var(--accent);
}

.snapshot-statistics-distribution progress {
  appearance: none;
  overflow: hidden;
  border-radius: var(--radius-full);
  background: var(--grid);
  color: var(--distribution-fill, var(--muted));
  accent-color: var(--distribution-fill, var(--muted));
}

.snapshot-statistics-distribution progress::-webkit-progress-bar {
  background: var(--grid);
}

.snapshot-statistics-distribution progress::-webkit-progress-value {
  background: var(--distribution-fill, var(--muted));
}

.snapshot-statistics-distribution progress::-moz-progress-bar {
  background: var(--distribution-fill, var(--muted));
}

.snapshot-statistic--male {
  --distribution-fill: var(--male);
}

.snapshot-statistic--female {
  --distribution-fill: var(--female);
}

.snapshot-statistic--unknown {
  --distribution-fill: var(--unknown);
}

.snapshot-statistic--institution {
  --distribution-fill: var(--institution);
}

/* Source values outside the canonical labels stay neutral and visibly distinct from unknown. */
.snapshot-statistic--other progress::-webkit-progress-value {
  background: repeating-linear-gradient(
    135deg,
    var(--muted) 0 var(--space-1),
    var(--surface-1) var(--space-1) var(--space-2)
  );
}

.snapshot-statistic--other progress::-moz-progress-bar {
  background: repeating-linear-gradient(
    135deg,
    var(--muted) 0 var(--space-1),
    var(--surface-1) var(--space-1) var(--space-2)
  );
}

.snapshot-statistic--unavailable {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  gap: var(--space-3);
  padding-block-end: var(--space-2);
  border-block-end: 1px solid var(--grid);
}

@container snapshot-detail (width < 42rem) {
  .snapshot-statistics-body {
    grid-template-columns: minmax(0, 1fr);
  }

  .snapshot-statistics-block + .snapshot-statistics-block {
    padding-block-start: var(--space-5);
    padding-inline-start: 0;
    border-block-start: 1px solid var(--border);
    border-inline-start: 0;
  }
}
</style>
