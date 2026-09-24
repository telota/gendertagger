<script setup lang="ts">
// One sidebar entry: an icon and a label. An entry without a target (the project has no run yet) is
// a disabled span rather than a dead link, so it is neither focusable nor announced as navigable.
import type { Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

defineProps<{
  to: RouteLocationRaw | null
  icon: Component
  label: string
}>()

const { t } = useI18n()
</script>

<template>
  <RouterLink v-if="to" :to="to" class="nav-item">
    <component :is="icon" class="nav-item-icon" :size="20" aria-hidden="true" />
    <span class="nav-item-label">{{ label }}</span>
  </RouterLink>
  <span
    v-else
    class="nav-item nav-item-disabled"
    aria-disabled="true"
    :title="t('nav.unavailable')"
  >
    <component :is="icon" class="nav-item-icon" :size="20" aria-hidden="true" />
    <span class="nav-item-label">{{ label }}</span>
  </span>
</template>

<style scoped>
.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  color: var(--text-secondary);
  font-size: var(--font-size-body-strong);
  text-decoration: none;
}

.nav-item-icon {
  flex-shrink: 0;
}

a.nav-item:hover {
  background: var(--surface-1);
}

a.nav-item.router-link-active {
  background: var(--surface-1);
  color: var(--accent);
  font-weight: var(--weight-semibold);
}

.nav-item-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Below 1080 px the sidebar is an icon rail (docs/23); the label stays available to assistive tech. */
@media (max-width: 1079px) {
  .nav-item {
    justify-content: center;
    padding: var(--space-2);
  }

  .nav-item-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}
</style>
