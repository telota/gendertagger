<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'

import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const router = useRouter()
const session = useSessionStore()

async function signOut(): Promise<void> {
  await session.logout()
  await router.push({ name: 'home' })
}
</script>

<template>
  <header class="app-header">
    <RouterLink :to="{ name: 'home' }" class="app-header-brand">{{ t('app.title') }}</RouterLink>
    <div v-if="session.status === 'ready'" class="app-header-session">
      <template v-if="session.isSignedIn">
        <span class="app-header-user">{{
          t('header.signedInAs', { name: session.user?.display_name })
        }}</span>
        <button type="button" class="app-header-signout" @click="signOut">
          {{ t('header.signOut') }}
        </button>
      </template>
      <RouterLink v-else :to="{ name: 'login' }" class="app-header-signin">{{
        t('header.signIn')
      }}</RouterLink>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}

.app-header-brand {
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  text-decoration: none;
}

.app-header-session {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--font-size-small);
}

.app-header-user {
  color: var(--text-secondary);
}

.app-header-signin,
.app-header-signout {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.app-header-signout {
  border: none;
  background: none;
  font: inherit;
  padding: 0;
  cursor: pointer;
}
</style>
