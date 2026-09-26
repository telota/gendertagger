<script setup lang="ts">
import { computed } from 'vue'

import { useSessionStore } from '@/stores/session'

import GuestHomeView from './GuestHomeView.vue'
import SignedInHomeView from './SignedInHomeView.vue'

const session = useSessionStore()

// Anything short of a confirmed session (idle, loading, error, or ready-but-signed-out) gets the
// public guest content: it is harmless to show and avoids a loading flash for the common case of an
// anonymous first visit.
const isSignedIn = computed(() => session.status === 'ready' && session.isSignedIn)
</script>

<template>
  <main class="home" :class="{ 'home--signed-in': isSignedIn }">
    <SignedInHomeView v-if="isSignedIn" />
    <GuestHomeView v-else />
  </main>
</template>

<style scoped>
.home {
  flex: 1;
  width: 100%;
  max-width: 40rem;
  margin: 0 auto;
  padding: var(--space-12) var(--space-4);
}

.home--signed-in {
  max-width: 60rem;
  padding-block: var(--space-8);
}
</style>
