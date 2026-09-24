<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { CANONICAL_LABELS } from '@/features/review/useVocabulary'

import './metric.css'
import type { MethodCoverage } from './reportSchema'

defineProps<{ rows: readonly MethodCoverage[] }>()

const { t, n } = useI18n()
</script>

<template>
  <section class="metric" aria-labelledby="coverage-heading">
    <h3 id="coverage-heading" class="metric-title">{{ t('evaluation.report.coverage.title') }}</h3>
    <p class="metric-note">{{ t('evaluation.report.coverage.note') }}</p>
    <div class="metric-scroll">
      <table class="metric-table">
        <caption class="metric-caption">
          {{
            t('evaluation.report.coverage.caption')
          }}
        </caption>
        <thead>
          <tr>
            <th scope="col">{{ t('evaluation.report.method') }}</th>
            <th scope="col" class="num">{{ t('evaluation.report.coverage.total') }}</th>
            <th scope="col" class="num">{{ t('evaluation.report.coverage.answered') }}</th>
            <th scope="col" class="num">{{ t('evaluation.report.coverage.share') }}</th>
            <th v-for="label in CANONICAL_LABELS" :key="label" scope="col" class="num token">
              {{ label }}
            </th>
            <th scope="col" class="num">{{ t('evaluation.report.coverage.abstained') }}</th>
            <th scope="col" class="num">{{ t('evaluation.report.coverage.errors') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.method_name">
            <th scope="row">{{ row.method_name }}</th>
            <td class="num">{{ n(row.total, 'integer') }}</td>
            <td class="num">{{ n(row.coverage_count, 'integer') }}</td>
            <td class="num">{{ n(row.coverage_share, 'ratio') }}</td>
            <td v-for="label in CANONICAL_LABELS" :key="label" class="num">
              {{ n(row.label_distribution[label] ?? 0, 'integer') }}
            </td>
            <td class="num">{{ n(row.abstain_count, 'integer') }}</td>
            <td class="num">{{ n(row.error_count, 'integer') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
