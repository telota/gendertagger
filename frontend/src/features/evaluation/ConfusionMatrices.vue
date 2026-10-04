<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import { CANONICAL_LABELS } from '@/composables/useVocabulary'

import './metric.css'
import type { BenchmarkSummary, MethodAccuracy } from './reportSchema'

defineProps<{ rows: readonly MethodAccuracy[]; benchmark: BenchmarkSummary }>()

const { t, n } = useI18n()
</script>

<template>
  <section class="metric app-card" aria-labelledby="confusion-heading">
    <h3 id="confusion-heading" class="metric-title">
      {{ t('evaluation.report.confusion.title') }}
    </h3>
    <p class="metric-note">{{ t('evaluation.report.confusion.note') }}</p>
    <div class="confusion-grid">
      <AppScrollRegion v-for="row in rows" :key="row.method_name" :label="row.method_name">
        <table class="metric-table confusion-table">
          <caption class="confusion-caption">
            {{
              row.method_name
            }}
          </caption>
          <thead>
            <tr>
              <th scope="col">{{ t('evaluation.report.confusion.truth') }}</th>
              <th v-for="label in CANONICAL_LABELS" :key="label" scope="col" class="num token">
                {{ label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="truth in benchmark.labels" :key="truth">
              <th scope="row" class="token">{{ truth }}</th>
              <td v-for="predicted in CANONICAL_LABELS" :key="predicted" class="num">
                {{ n(row.confusion_matrix[truth]?.[predicted] ?? 0, 'integer') }}
              </td>
            </tr>
          </tbody>
        </table>
      </AppScrollRegion>
    </div>
  </section>
</template>

<style scoped>
.confusion-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));
  gap: var(--space-4);
}

.confusion-caption {
  padding: 0 0 var(--space-1);
  font-weight: var(--weight-semibold);
  text-align: left;
}
</style>
