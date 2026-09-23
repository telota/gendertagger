<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'

import AppListbox from '@/components/base/AppListbox.vue'
import { useLocale } from '@/composables/useLocale'
import { useTheme, type ThemePreference } from '@/composables/useTheme'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const router = useRouter()
const session = useSessionStore()
const locale = useLocale()
const theme = useTheme()

const themeOptions = computed<{ value: ThemePreference; label: string }[]>(() => [
  { value: 'system', label: t('theme.system') },
  { value: 'light', label: t('theme.light') },
  { value: 'dark', label: t('theme.dark') },
])

async function signOut(): Promise<void> {
  await session.logout()
  await router.push({ name: 'home' })
}

function retry(): void {
  void session.initialize()
}
</script>

<template>
  <header class="app-header">
    <div class="app-header-controls">
      <AppListbox
        class="app-header-switcher app-header-switcher--locale"
        :label="t('locale.label')"
        :options="locale.options"
        :model-value="locale.current.value"
        @update:model-value="locale.setLocale"
      />
      <AppListbox
        class="app-header-switcher app-header-switcher--theme"
        :label="t('theme.label')"
        :options="themeOptions"
        :model-value="theme.preference.value"
        @update:model-value="theme.setPreference"
      />
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
      <div
        v-else-if="session.status === 'error'"
        class="app-header-session app-header-session-error"
      >
        <span role="alert" class="app-header-error">{{ t('header.serverError') }}</span>
        <button type="button" class="app-header-retry" @click="retry">
          {{ t('header.retry') }}
        </button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}

.app-header-controls {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.app-header-switcher {
  width: 8rem;
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

.app-header-error {
  color: var(--critical);
}

.app-header-retry {
  border: none;
  background: none;
  font: inherit;
  color: var(--accent);
  text-underline-offset: 0.2em;
  padding: 0;
  cursor: pointer;
}
</style>
