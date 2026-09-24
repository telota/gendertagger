<script setup lang="ts">
// A native <progress>: assistive technology already knows it, and it needs no ARIA of its own beyond
// the accessible name. The value is the server's percentage, never recomputed in the browser; a
// null percentage (unknown total) renders as the indeterminate state.
defineProps<{
  /** 0–100 as reported by the server, or null while the total is not yet known. */
  percentage: number | null
  label: string
}>()
</script>

<template>
  <progress
    class="app-progress"
    :aria-label="label"
    :max="100"
    :value="percentage ?? undefined"
  ></progress>
</template>

<style scoped>
.app-progress {
  width: 100%;
  height: 0.75rem;
  accent-color: var(--accent);
}
</style>
