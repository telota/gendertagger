<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppDialog from '@/components/base/AppDialog.vue'
import AppTextField from '@/components/base/AppTextField.vue'

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
    <AppButton v-if="isCurrentAccount" to="/change-password" variant="ghost">
      {{ t('admin.security.changeOwnPassword') }}
    </AppButton>
    <AppButton
      v-else
      type="button"
      variant="ghost"
      :disabled="isSubmitting"
      :aria-label="t('admin.security.reset.ariaLabel', { username: account.username })"
      @click="openConfirmation('resetPassword')"
    >
      {{ t('admin.security.reset.open') }}
    </AppButton>
    <AppButton
      type="button"
      variant="ghost"
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
      <h2 :id="`admin-user-reset-disclosure-${account.id}`">
        {{ t('admin.security.reset.successTitle', { username: disclosure.targetUsername }) }}
      </h2>
      <p>{{ t('admin.security.reset.successDescription') }}</p>
      <AppTextField
        :id="`admin-user-reset-password-${account.id}`"
        class="admin-user-password-field"
        :label="t('admin.security.reset.temporaryPassword')"
        readonly
        :model-value="disclosure.temporaryPassword"
        :aria-describedby="`admin-user-reset-password-help-${account.id}`"
      />
      <p :id="`admin-user-reset-password-help-${account.id}`">
        {{ t('admin.security.reset.temporaryPasswordHelp') }}
      </p>
      <AppButton type="button" variant="ghost" @click="emit('dismissResetDisclosure')">
        {{ t('admin.security.reset.dismissTemporaryPassword') }}
      </AppButton>
    </section>

    <AppDialog
      :open="confirmation !== null"
      class="admin-user-security-dialog"
      size="lg"
      actions-class="admin-user-security-confirmation-actions"
      @close="confirmation = null"
    >
      <template #title>
        {{
          confirmation === 'resetPassword'
            ? t('admin.security.reset.confirm.title', { username: account.username })
            : t('admin.security.revoke.confirm.title', { username: account.username })
        }}
      </template>
      <template v-if="confirmation === 'resetPassword'">
        <p class="admin-user-security-copy">{{ t('admin.security.reset.confirm.description') }}</p>
        <p class="admin-user-security-copy">{{ t('admin.security.reset.confirm.inactive') }}</p>
      </template>
      <template v-else>
        <p class="admin-user-security-copy">{{ t('admin.security.revoke.confirm.description') }}</p>
        <p v-if="isCurrentAccount" class="admin-user-security-copy">
          {{ t('admin.security.revoke.confirm.selfWarning') }}
        </p>
      </template>
      <template #actions>
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
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.admin-user-security-actions {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
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

.admin-user-reset-disclosure h2 {
  margin: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.admin-user-reset-disclosure p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.admin-user-password-field {
  --field-gap: var(--space-2);
  --field-label-size: inherit;
  --field-label-color: var(--text-primary);
  --field-control-width: 100%;
}

.admin-user-security-copy {
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
}

:global(.admin-user-security-dialog .app-dialog-actions.admin-user-security-confirmation-actions) {
  margin-top: var(--space-5);
}
</style>
