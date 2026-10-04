<script setup lang="ts">
import { useStatusLabel } from '@/composables/useStatusLabel'

withDefaults(defineProps<{ status: string; toned?: boolean }>(), { toned: true })
const label = useStatusLabel()
</script>

<template>
  <span class="lifecycle-status" :class="toned ? `lifecycle-status--${status}` : undefined">
    {{ label(status) }}
  </span>
</template>

<style scoped>
.lifecycle-status--completed {
  color: var(--good);
}
.lifecycle-status--failed,
.lifecycle-status--completed_with_errors {
  color: var(--critical-text);
}
</style>
