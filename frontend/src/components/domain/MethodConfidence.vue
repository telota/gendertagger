<script setup lang="ts">
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{ value: number | null | undefined; described?: boolean }>(), {
  described: false,
})
const { t, n } = useI18n()
</script>

<template>
  <template v-if="value != null">
    {{
      described
        ? t('runs.results.confidence', { value: n(value, 'confidence') })
        : n(value, 'confidence')
    }}
  </template>
  <span v-else
    ><slot>{{ t('review.none') }}</slot></span
  >
</template>
