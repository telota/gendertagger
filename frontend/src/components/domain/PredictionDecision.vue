<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { components } from '@/api/schema'
import VocabBadge from './VocabBadge.vue'
import MethodConfidence from './MethodConfidence.vue'
import MissingPrediction from './MissingPrediction.vue'

withDefaults(
  defineProps<{
    prediction:
      | Pick<components['schemas']['PredictionResult'], 'label' | 'raw_label' | 'method_confidence'>
      | null
      | undefined
    gloss?: string
    raw?: boolean
    method?: boolean
    missing?: boolean
  }>(),
  { gloss: '', raw: false, method: false, missing: false },
)
const { t } = useI18n()
</script>

<template>
  <VocabBadge :value="prediction?.label" :gloss="gloss" kind="label" />
  <template v-if="method">
    <div
      v-if="prediction?.raw_label || prediction?.method_confidence != null"
      class="prediction-decision-detail"
    >
      <span v-if="prediction?.raw_label">{{
        t('runs.results.rawLabel', { label: prediction.raw_label })
      }}</span>
      <span v-if="prediction?.method_confidence != null"
        ><MethodConfidence :value="prediction.method_confidence" described
      /></span>
    </div>
    <p v-else-if="missing" class="prediction-missing"><MissingPrediction method /></p>
  </template>
  <span v-else-if="raw && prediction?.raw_label" class="prediction-raw">{{
    t('review.detail.methods.raw', { raw: prediction.raw_label })
  }}</span>
</template>

<style scoped>
.prediction-raw {
  margin-left: var(--space-2);
  color: var(--text-secondary);
}
.prediction-decision-detail {
  display: grid;
  gap: var(--space-1);
  margin-block-start: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}
.prediction-missing {
  margin: var(--space-2) 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
</style>
