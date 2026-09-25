<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'

import { provideDraftNavigation } from '@/composables/useDraftNavigation'
import { usePreferencePresentation } from '@/composables/usePreferencePresentation'
import SessionRecoveryDialog from '@/features/auth/SessionRecoveryDialog.vue'
import { useSessionStore } from '@/stores/session'

import AppFooter from './AppFooter.vue'
import DraftLeaveDialog from './DraftLeaveDialog.vue'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import MobileNavigationDrawer from './MobileNavigationDrawer.vue'
import { useRouteFocus } from './useRouteFocus'

const { t } = useI18n()
provideDraftNavigation()
const mainContent = ref<HTMLElement | null>(null)
useRouteFocus(mainContent)
const session = useSessionStore()
const { desktopSidebarCollapsed } = usePreferencePresentation()
const mobileNavigationOpen = ref(false)
watch(
  () => session.canUsePrivateNavigation,
  (eligible) => {
    if (!eligible) mobileNavigationOpen.value = false
  },
)

onMounted(() => {
  void session.initialize()
})
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content" @click.prevent="mainContent?.focus()">
      {{ t('nav.skipToContent') }}
    </a>
    <AppSidebar
      v-if="session.canUsePrivateNavigation"
      :desktop-sidebar-collapsed="desktopSidebarCollapsed"
    />
    <div class="app-shell-content">
      <AppHeader
        :mobile-navigation-open="mobileNavigationOpen"
        @open-navigation="mobileNavigationOpen = true"
      />
      <div id="main-content" ref="mainContent" class="app-route-content" tabindex="-1">
        <RouterView />
      </div>
      <AppFooter />
    </div>
    <MobileNavigationDrawer v-if="session.canUsePrivateNavigation" v-model="mobileNavigationOpen" />
    <SessionRecoveryDialog />
    <DraftLeaveDialog />
  </div>
</template>

<style scoped>
.skip-link {
  position: fixed;
  z-index: 40;
  inset-block-start: var(--space-4);
  inset-inline-start: var(--space-4);
  max-width: calc(100% - 2 * var(--space-4));
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--accent);
}

.skip-link:not(:focus) {
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.app-route-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.app-shell {
  display: flex;
  min-height: 100vh;
}

.app-shell-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}
</style>
