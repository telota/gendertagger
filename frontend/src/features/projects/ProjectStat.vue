<script setup lang="ts">
// One figure. A critical tone only recolours the value; the label always says what is wrong, so the
// state never rests on colour alone.
withDefaults(defineProps<{ tone?: 'default' | 'critical' }>(), { tone: 'default' })
</script>

<template>
  <div class="stat">
    <dt class="stat-label"><slot name="label" /></dt>
    <dd class="stat-figure">
      <span class="stat-value" :class="{ 'stat-value--critical': tone === 'critical' }">
        <slot />
      </span>
      <span v-if="$slots.detail" class="stat-detail"><slot name="detail" /></span>
    </dd>
  </div>
</template>

<style scoped>
/* Two rows (label, figure) taken from the list's own rows, so the figures of one band line up even
   when their labels wrap onto different numbers of lines. Without subgrid support the two parts
   simply stack. */
.stat {
  display: grid;
  grid-row: span 2;
  grid-template-rows: subgrid;
  row-gap: var(--space-1);
  min-inline-size: 0;
}
.stat-label {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: var(--line-height-small);
}
.stat-figure {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-inline-size: 0;
  margin: 0;
}
.stat-value {
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-title);
  font-variant-numeric: tabular-nums;
}
.stat-value--critical {
  color: var(--critical-text);
}
.stat-detail {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: var(--line-height-small);
}
</style>
