<script setup lang="ts">
import { PhGenderIntersex, PhList } from '@phosphor-icons/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import { useSessionStore } from '@/stores/session'

import AccountMenu from './AccountMenu.vue'
import AppBreadcrumbs from './AppBreadcrumbs.vue'
import SidebarPreferences from './SidebarPreferences.vue'

defineProps<{ mobileNavigationOpen?: boolean }>()
defineEmits<{ openNavigation: [] }>()

const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()
</script>

<template>
  <header
    class="app-header"
    :class="{
      'app-header--public': !session.canUsePrivateNavigation,
      'app-header--private-home': session.canUsePrivateNavigation && route.name === 'home',
    }"
  >
    <button
      v-if="session.canUsePrivateNavigation"
      type="button"
      class="app-header-navigation"
      :aria-label="t('nav.openNavigation')"
      :aria-expanded="mobileNavigationOpen ?? false"
      aria-haspopup="dialog"
      @click="$emit('openNavigation')"
    >
      <PhList :size="24" aria-hidden="true" />
    </button>
    <AppBreadcrumbs
      v-if="session.canUsePrivateNavigation && route.name !== 'home'"
      class="app-header-location"
    />
    <RouterLink
      v-else-if="!session.canUsePrivateNavigation"
      :to="{ name: 'home' }"
      class="app-header-brand"
    >
      <PhGenderIntersex :size="24" aria-hidden="true" />
      <span>{{ t('app.title') }}</span>
    </RouterLink>
    <AccountMenu class="app-header-account" />
    <SidebarPreferences
      v-if="!session.canUsePrivateNavigation"
      presentation="header"
      class="app-header-preferences"
    />
  </header>
</template>

<style scoped>
.app-header {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  min-width: 0;
  min-height: var(--shell-header-height);
  align-items: center;
  gap: var(--space-3) var(--space-6);
  padding: var(--space-3) var(--page-gutter);
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}

.app-header-location {
  flex: 1 1 16rem;
}

.app-header-brand {
  display: inline-flex;
  flex: 1 1 auto;
  align-items: center;
  gap: var(--space-2);
  min-inline-size: 0;
  min-height: var(--control-min-size);
  color: var(--text-primary);
  font-weight: var(--weight-semibold);
  text-decoration: none;
}

.app-header-brand svg {
  flex-shrink: 0;
}

.app-header-brand span {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}

.app-header-preferences {
  flex: 0 1 auto;
  max-inline-size: 100%;
}

.app-header-account {
  max-inline-size: 100%;
  margin-inline-start: auto;
}

.app-header-navigation {
  display: none;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  min-width: var(--control-touch-size);
  min-height: var(--control-touch-size);
  padding: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-primary);
  cursor: pointer;
}

@media (width < 720px) {
  .app-header {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: var(--space-2) var(--space-3);
  }

  .app-header-navigation {
    display: flex;
    grid-column: 1;
    grid-row: 1;
  }

  .app-header-location {
    grid-column: 2;
    grid-row: 1;
  }

  .app-header-account {
    grid-column: 2;
    grid-row: 2;
  }

  .app-header--private-home .app-header-account {
    grid-row: 1;
  }

  .app-header--public {
    display: flex;
  }

  .app-header--public .app-header-brand {
    flex: 1 1 8rem;
  }

  .app-header--public .app-header-preferences {
    flex: 1 1 100%;
  }
}
</style>
