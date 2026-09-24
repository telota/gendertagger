<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import './metric.css'
import type { BenchmarkSummary, MethodAccuracy } from './reportSchema'

const props = defineProps<{
  rows: readonly MethodAccuracy[]
  benchmark: BenchmarkSummary
  /** From the evaluation's resolved configuration; null when it is not recorded there. */
  confidenceLevel: number | null
}>()

const { t, n } = useI18n()

// One line per method, with its recall for each benchmark label (or null if the report has none).
const lines = computed(() =>
  props.rows.map((row) => ({
    row,
    recalls: props.benchmark.labels.map((label) => ({
      label,
      recall: row.recall.find((entry) => entry.label === label) ?? null,
    })),
  })),
)

const level = computed(() =>
  props.confidenceLevel === null ? null : n(props.confidenceLevel * 100, 'integer'),
)
</script>

<template>
  <section class="metric" aria-labelledby="accuracy-heading">
    <h3 id="accuracy-heading" class="metric-title">{{ t('evaluation.report.accuracy.title') }}</h3>
    <p class="metric-note">{{ t('evaluation.report.accuracy.note') }}</p>
    <p class="metric-note">{{ t('evaluation.report.accuracy.effectiveNote') }}</p>
    <p class="metric-note">
      {{
        level === null
          ? t('evaluation.report.accuracy.recallNoteUnknown')
          : t('evaluation.report.accuracy.recallNote', { level })
      }}
    </p>
    <div class="metric-scroll">
      <table class="metric-table">
        <caption class="metric-caption">
          {{
            t('evaluation.report.accuracy.caption')
          }}
        </caption>
        <thead>
          <tr>
            <th scope="col">{{ t('evaluation.report.method') }}</th>
            <th scope="col" class="num">{{ t('evaluation.report.accuracy.answered') }}</th>
            <th scope="col" class="num">{{ t('evaluation.report.accuracy.correct') }}</th>
            <th scope="col" class="num">{{ t('evaluation.report.accuracy.accuracy') }}</th>
            <th scope="col" class="num">{{ t('evaluation.report.accuracy.effective') }}</th>
            <th v-for="label in benchmark.labels" :key="label" scope="col" class="num">
              {{ t('evaluation.report.accuracy.recall') }}
              <span class="token">{{ label }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="line in lines" :key="line.row.method_name">
            <th scope="row">{{ line.row.method_name }}</th>
            <td class="num">{{ n(line.row.answered_count, 'integer') }}</td>
            <td class="num">{{ n(line.row.correct_count, 'integer') }}</td>
            <td class="num">{{ n(line.row.accuracy, 'ratio') }}</td>
            <td class="num">{{ n(line.row.effective_accuracy, 'ratio') }}</td>
            <td v-for="entry in line.recalls" :key="entry.label" class="num">
              <template v-if="entry.recall">
                {{
                  t('evaluation.report.accuracy.recallCell', {
                    recall: n(entry.recall.recall, 'ratio'),
                    low: n(entry.recall.ci_low, 'ratio'),
                    high: n(entry.recall.ci_high, 'ratio'),
                    correct: n(entry.recall.correct, 'integer'),
                    size: n(entry.recall.class_size, 'integer'),
                  })
                }}
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
