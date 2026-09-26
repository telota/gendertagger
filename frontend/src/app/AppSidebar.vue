<script setup lang="ts">
import {
  PhArrowClockwise,
  PhGenderIntersex,
  PhHourglass,
  PhWarningCircle,
} from '@phosphor-icons/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import NavItem from './NavItem.vue'
import ProjectSwitcher from './ProjectSwitcher.vue'
import SidebarCollapseButton from './SidebarCollapseButton.vue'
import SidebarPreferences from './SidebarPreferences.vue'
import SidebarTooltip from './SidebarTooltip.vue'
import { useSidebarNavigation } from './useSidebarNavigation'
import { useProjectIdentity } from './useProjectIdentity'

defineProps<{ desktopSidebarCollapsed?: boolean; mobile?: boolean }>()

const { t } = useI18n()
const groups = useSidebarNavigation()
const { project } = useProjectIdentity()
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
        <ProjectSwitcher
          v-if="group.id === 'project' && project"
          :project="project"
          :desktop-collapsed="desktopSidebarCollapsed"
          :mobile="mobile"
        />
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
        <div v-if="group.availability" class="app-sidebar-availability">
          <p role="status">
            <component
              :is="group.availability.status === 'error' ? PhWarningCircle : PhHourglass"
              :size="20"
              aria-hidden="true"
            />
            <span class="app-sidebar-availability-label">{{
              group.availability.status === 'error'
                ? t('taskEntry.availabilityError')
                : t('taskEntry.availabilityLoading')
            }}</span>
          </p>
          <SidebarTooltip
            v-if="group.availability.status === 'error'"
            v-slot="{ triggerProps }"
            :text="`${t('taskEntry.availabilityError')} ${t('taskEntry.retryAvailability')}`"
            rail-only
            :desktop-collapsed="desktopSidebarCollapsed"
            :mobile="mobile"
          >
            <button
              v-bind="triggerProps"
              type="button"
              class="app-sidebar-availability-retry"
              :aria-label="t('taskEntry.retryAvailability')"
              @click="group.availability.retry"
            >
              <PhArrowClockwise :size="20" aria-hidden="true" />
              <span class="app-sidebar-availability-label">{{
                t('taskEntry.retryAvailability')
              }}</span>
            </button>
          </SidebarTooltip>
        </div>
      </div>
    </nav>
    <footer class="app-sidebar-footer">
      <SidebarPreferences :desktop-collapsed="desktopSidebarCollapsed" :mobile="mobile" />
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

.app-sidebar-availability {
  margin-top: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--font-size-body);
}

.app-sidebar-availability p,
.app-sidebar-availability-retry {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: 0;
  padding: var(--space-2) var(--space-3);
}

.app-sidebar-availability svg {
  flex-shrink: 0;
}

.app-sidebar-availability-retry {
  min-height: var(--space-10);
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.app-sidebar-availability-retry:hover {
  background: var(--surface-1);
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
  .app-sidebar--desktop-collapsed .app-sidebar-group,
  .app-sidebar--desktop-collapsed .app-sidebar-availability-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .app-sidebar--desktop-collapsed .app-sidebar-availability p,
  .app-sidebar--desktop-collapsed .app-sidebar-availability-retry {
    justify-content: center;
    padding: var(--space-2);
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
  .app-sidebar-group,
  .app-sidebar-availability-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .app-sidebar-availability p,
  .app-sidebar-availability-retry {
    justify-content: center;
    padding: var(--space-2);
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
