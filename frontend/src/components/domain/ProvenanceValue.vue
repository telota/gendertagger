<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ value: string | null | undefined }>()
const { t } = useI18n()
</script>

<template>
  <code v-if="value" class="provenance-value">{{ value }}</code>
  <span v-else class="provenance-missing">{{ t('runs.provenance.notRecorded') }}</span>
</template>

<style scoped>
.provenance-value {
  font-size: var(--font-size-small);
}
.provenance-missing {
  color: var(--text-secondary);
}
</style>
