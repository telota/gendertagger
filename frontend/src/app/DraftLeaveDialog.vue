<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppDialog from '@/components/base/AppDialog.vue'
import { useDraftNavigation } from '@/composables/useDraftNavigation'

const { t } = useI18n()
const navigation = useDraftNavigation()
</script>

<template>
  <AppDialog
    :open="navigation.isOpen.value"
    class="draft-leave"
    size="lg"
    scroll="panel"
    frame-inset="gutter"
    description-class="draft-leave-description"
    @close="navigation.resolveLeave(false)"
  >
    <template #title>{{ t('draftNavigation.title') }}</template>
    <template #description>{{ t('draftNavigation.body') }}</template>
    <template #actions>
      <AppButton type="button" variant="ghost" @click="navigation.resolveLeave(false)">
        {{ t('draftNavigation.stay') }}
      </AppButton>
      <AppButton type="button" @click="navigation.resolveLeave(true)">
        {{ t('draftNavigation.discard') }}
      </AppButton>
    </template>
  </AppDialog>
</template>

<style scoped>
/* The Headless UI portal root does not carry this component's scope attribute. */
:global(.app-dialog.draft-leave) {
  position: fixed;
  inset: 0;
  z-index: 50;
}

:global(.draft-leave .app-dialog-description.draft-leave-description) {
  margin-bottom: var(--space-5);
}
</style>
