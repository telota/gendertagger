<script setup lang="ts">
import { PhFolders } from '@phosphor-icons/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const session = useSessionStore()
const displayName = computed(() => session.user?.display_name ?? '')
</script>

<template>
  <div class="home-signed-in">
    <p class="home-signed-in-welcome">
      {{ t('home.signedIn.welcomeBack', { name: displayName }) }}
    </p>
    <AppButton :to="{ name: 'projects' }" class="home-signed-in-projects">
      <PhFolders :size="18" aria-hidden="true" />
      {{ t('home.signedIn.goToProjects') }}
    </AppButton>
  </div>
</template>

<style scoped>
.home-signed-in {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-5);
  margin-bottom: var(--space-12);
}

.home-signed-in-welcome {
  margin: 0;
  font-size: var(--font-size-title);
  line-height: var(--line-height-title);
  color: var(--text-primary);
}

.home-signed-in-projects {
  padding: var(--space-3) var(--space-5);
  font-size: var(--font-size-body-strong);
}
</style>
