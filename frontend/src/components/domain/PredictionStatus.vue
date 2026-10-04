<script setup lang="ts">
import type { components } from '@/api/schema'
import VocabBadge from './VocabBadge.vue'

withDefaults(
  defineProps<{
    status: components['schemas']['MethodExecutionResultState']
    gloss?: string
    display?: 'plain' | 'token' | 'badge'
  }>(),
  { gloss: '', display: 'plain' },
)
</script>

<template>
  <VocabBadge v-if="display === 'badge'" :value="status" :gloss="gloss" kind="state" />
  <template v-else>
    <span
      :class="
        display === 'token' ? ['prediction-status', `prediction-status--${status}`] : undefined
      "
      >{{ status }}</span
    >
    <span v-if="gloss" class="prediction-gloss">{{ gloss }}</span>
  </template>
</template>

<style scoped>
.prediction-status {
  font-family: var(--font-mono, ui-monospace, monospace);
}
.prediction-status--error {
  color: var(--critical-text);
}
.prediction-gloss {
  margin-left: var(--space-2);
  color: var(--text-secondary);
}
</style>
