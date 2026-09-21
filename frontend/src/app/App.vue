<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <main class="app-placeholder">
    <h1 class="app-placeholder-title">{{ t('app.title') }}</h1>
    <p class="app-placeholder-notice">{{ t('app.scaffoldNotice') }}</p>
  </main>
</template>

<style scoped>
.app-placeholder {
  max-width: 40rem;
  margin: 0 auto;
  padding: var(--space-12) var(--space-4);
}

.app-placeholder-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}

.app-placeholder-notice {
  margin: 0;
  color: var(--text-secondary);
}
</style>
