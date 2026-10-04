<script setup lang="ts">
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{ method?: boolean }>(), { method: false })
const { t } = useI18n()
</script>

<template>
  {{ method ? t('runs.results.noPrediction') : t('review.detail.methods.noPrediction') }}
</template>
