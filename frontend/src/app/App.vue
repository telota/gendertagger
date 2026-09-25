<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'

import { usePreferencePresentation } from '@/composables/usePreferencePresentation'
import SessionRecoveryDialog from '@/features/auth/SessionRecoveryDialog.vue'
import { useSessionStore } from '@/stores/session'

import AppFooter from './AppFooter.vue'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'

const session = useSessionStore()
const { desktopSidebarCollapsed } = usePreferencePresentation()

onMounted(() => {
  void session.initialize()
})
</script>

<template>
  <div class="app-shell">
    <AppSidebar :desktop-sidebar-collapsed="desktopSidebarCollapsed" />
    <div class="app-shell-content">
      <AppHeader />
      <RouterView />
      <AppFooter />
    </div>
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
