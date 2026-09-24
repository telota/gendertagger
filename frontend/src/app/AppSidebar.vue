<script setup lang="ts">
// The shell's one navigation surface (decision D7); the wireframe's second, redundant tab row is
// dropped. Layout per docs/25-frontend-design-guidelines.md: "a fixed sidebar plus a content region".
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useAdminAccess } from '@/composables/useAdminAccess'

const { t } = useI18n()
const { canAccessAdmin } = useAdminAccess()
</script>

<template>
  <aside class="app-sidebar">
    <RouterLink :to="{ name: 'home' }" class="app-sidebar-brand">{{ t('app.title') }}</RouterLink>
    <nav class="app-sidebar-nav" :aria-label="t('nav.label')">
      <ul class="app-sidebar-nav-list">
        <li>
          <RouterLink :to="{ name: 'projects' }" class="app-sidebar-nav-item">{{
            t('nav.projects')
          }}</RouterLink>
        </li>
        <li v-if="canAccessAdmin">
          <RouterLink :to="{ name: 'adminUsers' }" class="app-sidebar-nav-item">{{
            t('nav.administration')
          }}</RouterLink>
        </li>
      </ul>
    </nav>
  </aside>
</template>

<style scoped>
.app-sidebar {
  display: flex;
  flex-direction: column;
  width: 15rem;
  flex-shrink: 0;
  padding: var(--space-4);
  border-right: 1px solid var(--border);
  background: var(--panel);
}

.app-sidebar-brand {
  display: block;
  margin-bottom: var(--space-6);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  text-decoration: none;
}

.app-sidebar-nav-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.app-sidebar-nav-item {
  display: block;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  color: var(--text-secondary);
  font-size: var(--font-size-body-strong);
  text-decoration: none;
}

.app-sidebar-nav-item:hover {
  background: var(--surface-1);
}

.app-sidebar-nav-item.router-link-active {
  background: var(--surface-1);
  color: var(--accent);
  font-weight: var(--weight-semibold);
}
</style>
