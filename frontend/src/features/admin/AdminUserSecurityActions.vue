<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'

import type { AdminUserSecurityError, PasswordResetDisclosure } from './useAdminUserMutations'

type AdminUser = components['schemas']['AdminUser']
type SecurityAction = 'resetPassword' | 'revokeSessions'

const props = defineProps<{
  account: AdminUser
  actorUserId: string
  isSubmitting: boolean
  error: AdminUserSecurityError | null
  errorTargetUserId: string | null
  resetDisclosure: PasswordResetDisclosure | null
  resetDirectoryRefreshFailed: boolean
}>()

const emit = defineEmits<{
  resetPassword: [account: AdminUser]
  revokeSessions: [account: AdminUser]
  dismissResetDisclosure: []
}>()

const { t } = useI18n()
const confirmation = ref<SecurityAction | null>(null)
const isCurrentAccount = computed(() => props.account.id === props.actorUserId)
const isActionTarget = computed(() => props.errorTargetUserId === props.account.id)
const disclosure = computed(() => {
  const candidate = props.resetDisclosure
  return candidate?.operation === 'password_reset' && candidate.targetUserId === props.account.id
    ? candidate
    : null
})

function errorMessage(error: AdminUserSecurityError | null): string | null {
  switch (error) {
    case 'resource_not_found':
      return t('admin.security.errors.resourceNotFound')
    case 'password_change_required':
      return t('admin.security.errors.passwordChangeRequired')
    case 'forbidden':
      return t('admin.security.errors.forbidden')
    case 'validation_error':
      return t('admin.security.errors.validationError')
    case 'authentication_required':
      return t('admin.security.errors.authenticationRequired')
    case 'network_error':
      return t('admin.security.errors.networkError')
    case 'unexpected':
      return t('admin.security.errors.unexpected')
    case null:
      return null
  }
}

function openConfirmation(action: SecurityAction): void {
  if (!props.isSubmitting) confirmation.value = action
}

function confirm(): void {
  const action = confirmation.value
  if (action === null || props.isSubmitting) return

  confirmation.value = null
  if (action === 'resetPassword') emit('resetPassword', props.account)
  else emit('revokeSessions', props.account)
}
</script>

<template>
  <div class="admin-user-security-actions">
    <RouterLink v-if="isCurrentAccount" class="admin-user-security-link" to="/change-password">
      {{ t('admin.security.changeOwnPassword') }}
    </RouterLink>
    <AppButton
      v-else
      type="button"
      variant="text"
      :disabled="isSubmitting"
      :aria-label="t('admin.security.reset.ariaLabel', { username: account.username })"
      @click="openConfirmation('resetPassword')"
    >
      {{ t('admin.security.reset.open') }}
    </AppButton>
    <AppButton
      type="button"
      variant="text"
      :disabled="isSubmitting"
      :aria-label="t('admin.security.revoke.ariaLabel', { username: account.username })"
      @click="openConfirmation('revokeSessions')"
    >
      {{ t('admin.security.revoke.open') }}
    </AppButton>

    <p v-if="isActionTarget && errorMessage(error)" role="alert" class="admin-user-security-error">
      {{ errorMessage(error) }}
    </p>

    <p
      v-if="isActionTarget && resetDirectoryRefreshFailed"
      role="alert"
      class="admin-user-security-refresh-error"
    >
      {{ t('admin.security.reset.refreshFailed') }}
    </p>

    <section
      v-if="disclosure"
      class="admin-user-reset-disclosure"
      :aria-labelledby="`admin-user-reset-disclosure-${account.id}`"
      role="status"
    >
      <h3 :id="`admin-user-reset-disclosure-${account.id}`">
        {{ t('admin.security.reset.successTitle', { username: disclosure.targetUsername }) }}
      </h3>
      <p>{{ t('admin.security.reset.successDescription') }}</p>
      <label :for="`admin-user-reset-password-${account.id}`">
        {{ t('admin.security.reset.temporaryPassword') }}
      </label>
      <input
        :id="`admin-user-reset-password-${account.id}`"
        readonly
        :value="disclosure.temporaryPassword"
        :aria-describedby="`admin-user-reset-password-help-${account.id}`"
      />
      <p :id="`admin-user-reset-password-help-${account.id}`">
        {{ t('admin.security.reset.temporaryPasswordHelp') }}
      </p>
      <AppButton type="button" variant="ghost" @click="emit('dismissResetDisclosure')">
        {{ t('admin.security.reset.dismissTemporaryPassword') }}
      </AppButton>
    </section>

    <Dialog
      :open="confirmation !== null"
      class="admin-user-security-dialog"
      @close="confirmation = null"
    >
      <div class="admin-user-security-backdrop" aria-hidden="true" />
      <div class="admin-user-security-frame">
        <DialogPanel class="admin-user-security-panel">
          <template v-if="confirmation === 'resetPassword'">
            <DialogTitle class="admin-user-security-title">
              {{ t('admin.security.reset.confirm.title', { username: account.username }) }}
            </DialogTitle>
            <p>{{ t('admin.security.reset.confirm.description') }}</p>
            <p>{{ t('admin.security.reset.confirm.inactive') }}</p>
          </template>
          <template v-else>
            <DialogTitle class="admin-user-security-title">
              {{ t('admin.security.revoke.confirm.title', { username: account.username }) }}
            </DialogTitle>
            <p>{{ t('admin.security.revoke.confirm.description') }}</p>
            <p v-if="isCurrentAccount">{{ t('admin.security.revoke.confirm.selfWarning') }}</p>
          </template>
          <div class="admin-user-security-confirmation-actions">
            <AppButton type="button" variant="ghost" @click="confirmation = null">
              {{ t('admin.security.cancel') }}
            </AppButton>
            <AppButton type="button" tone="destructive" @click="confirm">
              {{
                confirmation === 'resetPassword'
                  ? t('admin.security.reset.confirm.submit')
                  : t('admin.security.revoke.confirm.submit')
              }}
            </AppButton>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  </div>
</template>

<style scoped>
.admin-user-security-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.admin-user-security-link {
  padding: var(--space-1) var(--space-2);
  color: var(--accent);
  font-weight: var(--weight-semibold);
  text-decoration: none;
  text-underline-offset: 0.2em;
}

.admin-user-security-link:hover {
  text-decoration: underline;
}

.admin-user-security-error,
.admin-user-security-refresh-error {
  width: 100%;
  margin: 0;
  color: var(--critical-text);
  font-size: var(--font-size-small);
}

.admin-user-reset-disclosure {
  display: grid;
  width: 100%;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--surface-1);
}

.admin-user-reset-disclosure h3 {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.admin-user-reset-disclosure p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.admin-user-reset-disclosure input {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
}

.admin-user-security-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
}

.admin-user-security-frame {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
}

.admin-user-security-panel {
  width: 100%;
  max-width: 30rem;
  padding: var(--space-6);
  border-radius: var(--radius-modal);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.admin-user-security-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
}

.admin-user-security-panel p {
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
}

.admin-user-security-confirmation-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-5);
}
</style>
