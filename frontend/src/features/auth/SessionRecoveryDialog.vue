<script setup lang="ts">
// Behaviour (focus trap, Escape-to-close, focus restore) comes from the D9 library; appearance is
// ours, matching AppListbox's split. This is the shell's first use of Dialog rather than Listbox.
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useSessionRecovery } from '@/composables/useSessionRecovery'

import { useLoginForm } from './useLoginForm'

const { t } = useI18n()
const recovery = useSessionRecovery()
// "Keep me signed in" is deliberately left out here: this is a quick recovery of the page the user
// was already on, not a fresh sign-in decision, so it defaults to the form's own unchecked default.
const {
  username,
  password,
  isSubmitting,
  errorMessage,
  submitLabel,
  submit: attemptLogin,
} = useLoginForm()

async function submit(): Promise<void> {
  const succeeded = await attemptLogin()
  if (succeeded) recovery.resolve()
}

function cancel(): void {
  recovery.reject(new Error('The user declined to sign in again.'))
}
</script>

<template>
  <Dialog :open="recovery.isOpen.value" class="session-recovery" @close="cancel">
    <div class="session-recovery-backdrop" aria-hidden="true" />
    <div class="session-recovery-frame">
      <DialogPanel class="session-recovery-panel">
        <DialogTitle class="session-recovery-title">{{ t('sessionRecovery.title') }}</DialogTitle>
        <p class="session-recovery-description">{{ t('sessionRecovery.description') }}</p>
        <form novalidate class="session-recovery-form" @submit.prevent="submit">
          <AppTextField
            id="session-recovery-username"
            v-model="username"
            name="username"
            :label="t('login.username')"
            autocomplete="username"
            required
          />
          <AppTextField
            id="session-recovery-password"
            v-model="password"
            name="password"
            type="password"
            :label="t('login.password')"
            autocomplete="current-password"
            required
          />
          <p v-if="errorMessage" role="alert" class="session-recovery-error">
            {{ errorMessage }}
          </p>
          <div class="session-recovery-actions">
            <AppButton
              class="session-recovery-cancel"
              variant="ghost"
              type="button"
              @click="cancel"
            >
              {{ t('sessionRecovery.cancel') }}
            </AppButton>
            <AppButton type="submit" :disabled="isSubmitting">{{ submitLabel }}</AppButton>
          </div>
        </form>
      </DialogPanel>
    </div>
  </Dialog>
</template>

<style scoped>
.session-recovery-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
}

.session-recovery-frame {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
}

.session-recovery-panel {
  width: 100%;
  max-width: 24rem;
  padding: var(--space-6);
  border-radius: var(--radius-modal);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.session-recovery-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
}

.session-recovery-description {
  margin: 0 0 var(--space-4);
  color: var(--text-secondary);
}

.session-recovery-form {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
}

.session-recovery-error {
  margin: 0;
  color: var(--critical-text);
}

.session-recovery-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}
</style>
