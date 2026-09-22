<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'

import { useSessionStore } from '@/stores/session'

import AppFooter from './AppFooter.vue'
import AppHeader from './AppHeader.vue'

const session = useSessionStore()

onMounted(() => {
  void session.initialize()
})
</script>

<template>
  <div class="app-shell">
    <AppHeader />
    <RouterView />
    <AppFooter />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
</style>
