<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n()
</script>

<template>
  <main class="not-found">
    <h1 class="not-found-title">{{ t('notFound.title') }}</h1>
    <p>{{ t('notFound.explanation') }}</p>
    <p>
      <RouterLink :to="{ name: 'home' }">{{ t('notFound.backToStart') }}</RouterLink>
    </p>
  </main>
</template>

<style scoped>
.not-found {
  flex: 1;
  width: 100%;
  max-width: 40rem;
  margin: 0 auto;
  padding: var(--space-12) var(--space-4);
}

.not-found-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}

.not-found a {
  color: var(--accent);
  text-underline-offset: 0.2em;
}
</style>
