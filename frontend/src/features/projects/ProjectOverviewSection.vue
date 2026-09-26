<script setup lang="ts">
// One hairline-divided section of the project overview card. Without a title it is plain content;
// with one, the heading names the region for assistive technology.
import { useId } from 'vue'

defineProps<{ title?: string }>()
const headingId = useId()
</script>

<template>
  <section class="overview-section" :aria-labelledby="title ? headingId : undefined">
    <h2 v-if="title" :id="headingId" class="overview-section-title">{{ title }}</h2>
    <slot />
  </section>
</template>

<style scoped>
.overview-section {
  min-inline-size: 0;
  padding: var(--space-4);
  overflow-wrap: anywhere;
}
.overview-section + .overview-section {
  border-block-start: 1px solid var(--border);
}
.overview-section-title {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-title);
}
</style>
