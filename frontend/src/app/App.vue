<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterView } from 'vue-router'

import { usePreferencePresentation } from '@/composables/usePreferencePresentation'
import SessionRecoveryDialog from '@/features/auth/SessionRecoveryDialog.vue'
import { useSessionStore } from '@/stores/session'

import AppFooter from './AppFooter.vue'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import MobileNavigationDrawer from './MobileNavigationDrawer.vue'

const session = useSessionStore()
const { desktopSidebarCollapsed } = usePreferencePresentation()
const mobileNavigationOpen = ref(false)

onMounted(() => {
  void session.initialize()
})
</script>

<template>
  <div class="app-shell">
    <AppSidebar :desktop-sidebar-collapsed="desktopSidebarCollapsed" />
    <div class="app-shell-content">
      <AppHeader
        :mobile-navigation-open="mobileNavigationOpen"
        @open-navigation="mobileNavigationOpen = true"
      />
      <RouterView />
      <AppFooter />
    </div>
    <MobileNavigationDrawer v-model="mobileNavigationOpen" />
    <SessionRecoveryDialog />
  </div>
</template>

<style scoped>
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
