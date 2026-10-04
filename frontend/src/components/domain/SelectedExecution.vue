<script setup lang="ts">
import type { components } from '@/api/schema'
import LifecycleStatus from './LifecycleStatus.vue'

withDefaults(
  defineProps<{
    id: string
    execution: Pick<
      components['schemas']['MethodExecutionSummary'],
      'method_name' | 'implementation_version' | 'status'
    > | null
    showStatus?: boolean
  }>(),
  { showStatus: false },
)
</script>

<template>
  <template v-if="execution">
    <span class="selected-execution-method">{{ execution.method_name }}</span>
    <span :class="{ 'selected-execution-version': showStatus }">{{
      execution.implementation_version
    }}</span>
    <LifecycleStatus v-if="showStatus" :status="execution.status" :toned="false" />
  </template>
  <code v-else :class="{ 'selected-execution-id': showStatus }">{{ id }}</code>
</template>

<style scoped>
.selected-execution-method {
  font-weight: var(--weight-semibold);
}
.selected-execution-version {
  color: var(--text-secondary);
}
.selected-execution-id {
  font-size: var(--font-size-small);
}
</style>
