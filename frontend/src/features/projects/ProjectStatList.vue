<script setup lang="ts">
// A row of labelled figures: label above value, wrapping onto further rows instead of shrinking.
// Items are `ProjectStat`s.
</script>

<template>
  <dl class="stat-list"><slot /></dl>
</template>

<style scoped>
.stat-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 9rem), 1fr));
  gap: var(--space-4) var(--space-6);
  margin: 0;
}
</style>
