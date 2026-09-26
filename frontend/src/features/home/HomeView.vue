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
  <main class="home app-page-frame" :class="{ 'app-page-frame--reading': !isSignedIn }">
    <SignedInHomeView v-if="isSignedIn" />
    <GuestHomeView v-else />
  </main>
</template>
