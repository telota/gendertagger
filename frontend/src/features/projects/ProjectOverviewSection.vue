<script setup lang="ts">
// One hairline-divided section of the project overview card. Without a title it is plain content;
// with one, the heading names the region for assistive technology. `eyebrow` is an optional small
// label above the title (the guided project page's "Schritt N", naming this section's place in its
// otherwise unnumbered sequence — advanced-presentation callers never pass it).
import { useId } from 'vue'

defineProps<{ title?: string; eyebrow?: string }>()
const headingId = useId()
</script>

<template>
  <section class="overview-section" :aria-labelledby="title ? headingId : undefined">
    <p v-if="eyebrow && title" class="overview-section-eyebrow">{{ eyebrow }}</p>
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
.overview-section-eyebrow {
  margin: 0 0 var(--space-1);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.overview-section-title {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-title);
}
</style>
