<script setup lang="ts">
import { RouterView } from 'vue-router'

import AppFooter from './AppFooter.vue'
</script>

<template>
  <div class="app-shell">
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
