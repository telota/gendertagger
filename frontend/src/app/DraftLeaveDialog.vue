<script setup lang="ts">
import { Dialog, DialogDescription, DialogPanel, DialogTitle } from '@headlessui/vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import { useDraftNavigation } from '@/composables/useDraftNavigation'

const { t } = useI18n()
const navigation = useDraftNavigation()
</script>

<template>
  <Dialog
    :open="navigation.isOpen.value"
    class="draft-leave"
    @close="navigation.resolveLeave(false)"
  >
    <div class="draft-leave-backdrop" aria-hidden="true" />
    <div class="draft-leave-frame">
      <DialogPanel class="draft-leave-panel">
        <DialogTitle class="draft-leave-title">{{ t('draftNavigation.title') }}</DialogTitle>
        <DialogDescription class="draft-leave-description">{{
          t('draftNavigation.body')
        }}</DialogDescription>
        <div class="draft-leave-actions">
          <AppButton type="button" variant="ghost" @click="navigation.resolveLeave(false)">
            {{ t('draftNavigation.stay') }}
          </AppButton>
          <AppButton type="button" @click="navigation.resolveLeave(true)">
            {{ t('draftNavigation.discard') }}
          </AppButton>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>

<style scoped>
/* The Headless UI portal root does not carry this component's scope attribute. */
:global(.draft-leave) {
  position: fixed;
  inset: 0;
  z-index: 50;
}

.draft-leave-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
}

.draft-leave-frame {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow-y: auto;
  padding: var(--page-gutter);
}

.draft-leave-panel {
  min-width: 0;
  width: 100%;
  max-width: 30rem;
  max-height: calc(100dvh - 2 * var(--page-gutter));
  overflow-y: auto;
  overflow-wrap: anywhere;
  padding: var(--space-6);
  border-radius: var(--radius-modal);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.draft-leave-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
}

.draft-leave-description {
  margin: 0 0 var(--space-5);
  color: var(--text-secondary);
}

.draft-leave-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-3);
}
</style>
