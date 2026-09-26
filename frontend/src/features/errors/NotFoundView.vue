<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n()
</script>

<template>
  <main class="not-found app-page-frame app-page-frame--reading">
    <header class="not-found-heading app-page-heading">
      <h1 class="not-found-title app-page-heading__title">{{ t('notFound.title') }}</h1>
    </header>
    <section class="not-found-content app-card">
      <p>{{ t('notFound.explanation') }}</p>
      <p>
        <RouterLink :to="{ name: 'home' }">{{ t('notFound.backToStart') }}</RouterLink>
      </p>
    </section>
  </main>
</template>

<style scoped>
.not-found a {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.not-found-content p {
  margin: 0;
}

.not-found-content p + p {
  margin-block-start: var(--space-3);
}
</style>
