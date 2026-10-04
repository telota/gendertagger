<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{ value: unknown; summary?: string; ruled?: boolean; compact?: boolean }>(),
  { ruled: false, compact: false },
)
const json = computed(() => JSON.stringify(props.value, null, 2))
</script>

<template>
  <details v-if="summary" class="json-disclosure" :class="{ 'json-disclosure--compact': compact }">
    <summary>{{ summary }}</summary>
    <pre class="json-data" :class="{ 'json-data--ruled': ruled }">{{ json }}</pre>
  </details>
  <pre v-else class="json-data json-data--visible" :class="{ 'json-data--ruled': ruled }">{{
    json
  }}</pre>
</template>

<style scoped>
.json-disclosure summary {
  cursor: pointer;
  font-weight: var(--weight-semibold);
}
.json-disclosure--compact summary {
  display: flex;
  width: fit-content;
  min-block-size: 2rem;
  align-items: center;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: normal;
}
.json-data {
  margin: var(--space-2) 0 0;
  padding: var(--space-3);
  overflow-x: auto;
  border-radius: var(--radius-input);
  background: var(--surface-1);
  font-size: var(--font-size-small);
}
.json-data--visible {
  margin: 0;
}
.json-data--ruled {
  border-radius: 0;
  border-inline-start: 2px solid var(--grid);
}
@media (pointer: coarse) {
  .json-disclosure--compact summary {
    min-block-size: 2.75rem;
  }
}
</style>
