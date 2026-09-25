<script setup lang="ts">
import { PhGearSix, PhGenderIntersex } from '@phosphor-icons/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useSessionStore } from '@/stores/session'

import NavItem from './NavItem.vue'
import SidebarCollapseButton from './SidebarCollapseButton.vue'
import SidebarPreferences from './SidebarPreferences.vue'
import { useSidebarNavigation } from './useSidebarNavigation'

defineProps<{ desktopSidebarCollapsed?: boolean; mobile?: boolean }>()

const { t } = useI18n()
const groups = useSidebarNavigation()
const session = useSessionStore()
</script>

<template>
  <aside
    class="app-sidebar"
    :class="{
      'app-sidebar--desktop-collapsed': desktopSidebarCollapsed && !mobile,
      'app-sidebar--mobile': mobile,
    }"
  >
    <RouterLink :to="{ name: 'home' }" class="app-sidebar-brand">
      <PhGenderIntersex :size="24" aria-hidden="true" />
      <span class="app-sidebar-brand-label">{{ t('app.title') }}</span>
    </RouterLink>
    <nav v-if="groups.length" class="app-sidebar-nav" :aria-label="t('nav.label')">
      <div v-for="group in groups" :key="group.id" class="app-sidebar-section">
        <h2 v-if="group.label" class="app-sidebar-group">{{ group.label }}</h2>
        <ul class="app-sidebar-nav-list">
          <li v-for="item in group.items" :key="item.id">
            <NavItem
              :desktop-collapsed="desktopSidebarCollapsed"
              :mobile="mobile"
              :to="item.to"
              :icon="item.icon"
              :label="item.label"
              :current="item.current"
              :unavailable-reason="item.unavailableReason"
            />
          </li>
        </ul>
      </div>
    </nav>
    <footer class="app-sidebar-footer">
      <SidebarPreferences :desktop-collapsed="desktopSidebarCollapsed" :mobile="mobile" />
      <NavItem
        v-if="session.canUsePrivateNavigation"
        :to="{ name: 'userSettings' }"
        :icon="PhGearSix"
        :label="t('header.settings')"
        :desktop-collapsed="desktopSidebarCollapsed"
        :mobile="mobile"
      />
      <SidebarCollapseButton v-if="!mobile" />
    </footer>
  </aside>
</template>

<style scoped>
.app-sidebar {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  width: var(--sidebar-width);
  height: 100dvh;
  flex-shrink: 0;
  padding: var(--space-4);
  border-right: 1px solid var(--border);
  background: var(--panel);
  transition: width var(--sidebar-transition) ease-out;
}

.app-sidebar-brand {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--space-10);
  margin-bottom: var(--space-4);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  text-decoration: none;
}

.app-sidebar-brand svg {
  flex-shrink: 0;
}

.app-sidebar-nav {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-1);
  margin: calc(-1 * var(--space-1));
  scrollbar-width: thin;
}

.app-sidebar-footer {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  gap: var(--space-2);
  margin-top: auto;
}

.app-sidebar-section + .app-sidebar-section {
  margin-top: var(--space-5);
}

.app-sidebar-group {
  margin: 0 0 var(--space-2);
  padding: 0 var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-size-body);
  font-weight: var(--weight-semibold);
}

.app-sidebar-nav-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

@media (min-width: 1080px) {
  .app-sidebar--desktop-collapsed {
    width: var(--sidebar-rail-width);
    padding: var(--space-4) var(--space-2);
  }

  .app-sidebar--desktop-collapsed .app-sidebar-brand {
    justify-content: center;
  }

  .app-sidebar--desktop-collapsed .app-sidebar-brand-label,
  .app-sidebar--desktop-collapsed .app-sidebar-group {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}

@media (720px <= width < 1080px) {
  .app-sidebar {
    width: var(--sidebar-rail-width);
    padding: var(--space-4) var(--space-2);
  }

  .app-sidebar-brand {
    justify-content: center;
  }

  .app-sidebar-brand-label,
  .app-sidebar-group {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}

@media (width < 720px) {
  .app-sidebar:not(.app-sidebar--mobile) {
    display: none;
  }
}

.app-sidebar--mobile {
  position: static;
  width: 100%;
  height: auto;
  flex: 1;
  min-height: 0;
  border: 0;
  padding-top: 0;
}
</style>
