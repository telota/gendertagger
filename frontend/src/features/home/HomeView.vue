<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useSessionStore } from '@/stores/session'

import GuestHomeView from './GuestHomeView.vue'
import SignedInHomeView from './SignedInHomeView.vue'

const { t } = useI18n()
const session = useSessionStore()

// Anything short of a confirmed session (idle, loading, error, or ready-but-signed-out) gets the
// public guest content: it is harmless to show and avoids a loading flash for the common case of an
// anonymous first visit.
const isSignedIn = computed(() => session.status === 'ready' && session.isSignedIn)
</script>

<template>
  <main class="home">
    <h1 class="home-title">{{ t('app.title') }}</h1>

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

.home-title {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}
</style>
