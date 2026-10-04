<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppDialog from '@/components/base/AppDialog.vue'
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

// The dialog's parent stays mounted while Headless UI removes its hidden fields.
watch(
  recovery.isOpen,
  () => {
    password.value = ''
    errorMessage.value = null
  },
  { flush: 'sync' },
)

async function submit(): Promise<void> {
  const succeeded = await attemptLogin()
  if (succeeded) recovery.resolve()
}

function cancel(): void {
  recovery.reject(new Error('The user declined to sign in again.'))
}
</script>

<template>
  <AppDialog
    :open="recovery.isOpen.value"
    class="session-recovery"
    size="sm"
    actions-class="session-recovery-actions"
    @close="cancel"
  >
    <template #title>{{ t('sessionRecovery.title') }}</template>
    <template #description>{{ t('sessionRecovery.description') }}</template>
    <form
      id="session-recovery-form"
      novalidate
      class="session-recovery-form"
      @submit.prevent="submit"
    >
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
    </form>
    <template #actions>
      <AppButton class="session-recovery-cancel" variant="ghost" type="button" @click="cancel">
        {{ t('sessionRecovery.cancel') }}
      </AppButton>
      <AppButton type="submit" form="session-recovery-form" :disabled="isSubmitting">
        {{ submitLabel }}
      </AppButton>
    </template>
  </AppDialog>
</template>

<style scoped>
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

:global(.session-recovery .app-dialog-actions.session-recovery-actions) {
  margin-top: var(--space-4);
}
</style>
