<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import AppScrollRegion from '@/components/base/AppScrollRegion.vue'

import './metric.css'
import type { KappaCell } from './reportSchema'

const props = defineProps<{ cells: readonly KappaCell[] }>()

const { t, n } = useI18n()

// One cell per unordered pair, generated in roster order, so the roster is the order of first
// appearance; the matrix is shown in both directions because a reader looks up either.
const methods = computed(() => {
  const order: string[] = []
  for (const cell of props.cells) {
    for (const name of [cell.method_a, cell.method_b]) {
      if (!order.includes(name)) order.push(name)
    }
  }
  return order
})

const byPair = computed(() => {
  const map = new Map<string, KappaCell>()
  for (const cell of props.cells) {
    map.set(`${cell.method_a}|${cell.method_b}`, cell)
    map.set(`${cell.method_b}|${cell.method_a}`, cell)
  }
  return map
})

// The rows of the shown matrix: the diagonal has no cell, every other position has its pair.
const matrix = computed(() =>
  methods.value.map((row) => ({
    row,
    cells: methods.value.map((column) => ({
      column,
      cell: row === column ? null : (byPair.value.get(`${row}|${column}`) ?? null),
    })),
  })),
)
const DASH = '—'
</script>

<template>
  <section class="metric app-card" aria-labelledby="kappa-heading">
    <h3 id="kappa-heading" class="metric-title">{{ t('evaluation.report.kappa.title') }}</h3>
    <p class="metric-note">{{ t('evaluation.report.kappa.note') }}</p>
    <p class="metric-note">{{ t('evaluation.report.kappa.undefinedNote') }}</p>
    <AppScrollRegion :label="t('evaluation.report.kappa.caption')">
      <table class="metric-table">
        <caption class="metric-caption">
          {{
            t('evaluation.report.kappa.caption')
          }}
        </caption>
        <thead>
          <tr>
            <th scope="col">{{ t('evaluation.report.method') }}</th>
            <th v-for="name in methods" :key="name" scope="col" class="num">{{ name }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="line in matrix" :key="line.row">
            <th scope="row">{{ line.row }}</th>
            <td v-for="entry in line.cells" :key="entry.column" class="num">
              <span v-if="entry.cell === null" aria-hidden="true">{{ DASH }}</span>
              <template v-else>
                <template v-if="entry.cell.kappa !== null">{{
                  n(entry.cell.kappa, 'ratio')
                }}</template>
                <span
                  v-else
                  class="kappa-undefined"
                  :title="t('evaluation.report.kappa.undefined')"
                >
                  {{ t('evaluation.report.kappa.undefinedShort') }}
                </span>
                <span class="metric-muted kappa-count">{{
                  t('evaluation.report.kappa.coAnswered', {
                    count: n(entry.cell.co_answered_count, 'integer'),
                  })
                }}</span>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </AppScrollRegion>
  </section>
</template>

<style scoped>
.kappa-count {
  display: block;
  font-size: var(--font-size-small);
}
</style>
