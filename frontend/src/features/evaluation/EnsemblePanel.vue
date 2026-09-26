<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import {
  AGREEMENT_TIERS,
  CANONICAL_LABELS,
  CERTAINTY_TIERS,
  useVocabularyGloss,
  type AgreementTier,
  type CertaintyTier,
} from '@/features/review/useVocabulary'

import './metric.css'
import type { EnsembleMetrics } from './reportSchema'

defineProps<{ ensemble: EnsembleMetrics | null }>()

const { t, n } = useI18n()
const gloss = useVocabularyGloss()
</script>

<template>
  <section class="metric app-card" aria-labelledby="ensemble-heading">
    <h3 id="ensemble-heading" class="metric-title">{{ t('evaluation.report.ensemble.title') }}</h3>
    <p v-if="!ensemble" class="metric-note">{{ t('evaluation.report.ensemble.none') }}</p>
    <template v-else>
      <p class="metric-note">{{ t('evaluation.report.ensemble.note') }}</p>
      <div class="ensemble-grid">
        <AppScrollRegion :label="t('evaluation.report.ensemble.labels')">
          <table class="metric-table ensemble-table">
            <caption class="ensemble-caption">
              {{
                t('evaluation.report.ensemble.labels')
              }}
            </caption>
            <tbody>
              <tr v-for="label in CANONICAL_LABELS" :key="label">
                <th scope="row" class="token">{{ label }}</th>
                <td class="num">
                  {{ n(ensemble.canonical_label_distribution[label] ?? 0, 'integer') }}
                </td>
              </tr>
            </tbody>
          </table>
        </AppScrollRegion>

        <AppScrollRegion :label="t('evaluation.report.ensemble.agreement')">
          <table class="metric-table ensemble-table">
            <caption class="ensemble-caption">
              {{
                t('evaluation.report.ensemble.agreement')
              }}
            </caption>
            <tbody>
              <tr v-for="tier in AGREEMENT_TIERS" :key="tier">
                <th scope="row">
                  <span class="token">{{ tier }}</span>
                  <span class="metric-muted"> {{ gloss.agreement(tier as AgreementTier) }}</span>
                </th>
                <td class="num">
                  {{ n(ensemble.agreement_tier_distribution[tier] ?? 0, 'integer') }}
                </td>
              </tr>
            </tbody>
          </table>
        </AppScrollRegion>

        <AppScrollRegion :label="t('evaluation.report.ensemble.certainty')">
          <table class="metric-table ensemble-table">
            <caption class="ensemble-caption">
              {{
                t('evaluation.report.ensemble.certainty')
              }}
            </caption>
            <tbody>
              <tr v-for="tier in CERTAINTY_TIERS" :key="tier">
                <th scope="row">
                  <span class="token">{{ tier }}</span>
                  <span class="metric-muted"> {{ gloss.certainty(tier as CertaintyTier) }}</span>
                </th>
                <td class="num">
                  {{ n(ensemble.certainty_tier_distribution[tier] ?? 0, 'integer') }}
                </td>
              </tr>
            </tbody>
          </table>
        </AppScrollRegion>
      </div>
      <p class="ensemble-review">
        {{
          t('evaluation.report.ensemble.review', {
            reviewed: n(ensemble.human_reviewed_count, 'integer'),
            corrected: n(ensemble.human_correction_count, 'integer'),
          })
        }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.ensemble-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 18rem), 1fr));
  gap: var(--space-4);
}

.ensemble-caption {
  padding: 0 0 var(--space-1);
  font-weight: var(--weight-semibold);
  text-align: left;
}

.ensemble-review {
  margin: 0;
  font-size: var(--font-size-small);
}
</style>
