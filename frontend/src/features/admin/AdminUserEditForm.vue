<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'

import type { AdminUserMutationError } from './useAdminUserMutations'

type AdminUser = components['schemas']['AdminUser']
type GlobalRole = components['schemas']['GlobalRole']
type AdminUserUpdate = components['schemas']['AdminUserUpdate']

const props = defineProps<{
  account: AdminUser
  actorUserId: string
  isSubmitting: boolean
  error: AdminUserMutationError | null
}>()

const emit = defineEmits<{
  cancel: []
  save: [command: AdminUserUpdate]
}>()

const { t } = useI18n()
const displayName = ref(props.account.display_name)
const roles = ref<GlobalRole[]>([...props.account.roles])
const isActive = ref(props.account.is_active)
const hasSubmitted = ref(false)
const isDeactivationConfirmationOpen = ref(false)

const isCurrentAccount = computed(() => props.account.id === props.actorUserId)
const displayNameError = computed(() => {
  if (!hasSubmitted.value) return undefined
  if (displayName.value.trim() === '') return t('admin.editing.validation.displayNameRequired')
  if (displayName.value.length > 200) return t('admin.editing.validation.displayNameLength')
  return undefined
})
const rolesChanged = computed(() =>
  (['admin', 'operator'] as const).some(
    (role) => roles.value.includes(role) !== props.account.roles.includes(role),
  ),
)
const updateCommand = computed<AdminUserUpdate>(() => {
  const command: AdminUserUpdate = {}
  if (displayName.value !== props.account.display_name) command.display_name = displayName.value
  if (rolesChanged.value) command.roles = [...roles.value]
  if (isActive.value !== props.account.is_active) command.is_active = isActive.value
  return command
})
const hasChanges = computed(() => Object.keys(updateCommand.value).length > 0)
const isDeactivation = computed(() => props.account.is_active && !isActive.value)

function resetDraft(): void {
  displayName.value = props.account.display_name
  roles.value = [...props.account.roles]
  isActive.value = props.account.is_active
  hasSubmitted.value = false
  isDeactivationConfirmationOpen.value = false
}

useDraftRegistration(() => hasChanges.value, resetDraft)

function errorMessage(error: AdminUserMutationError | null): string | null {
  switch (error) {
    case 'username_conflict':
      return t('admin.errors.usernameConflict')
    case 'self_deactivation_forbidden':
      return t('admin.errors.selfDeactivationForbidden')
    case 'self_admin_role_removal_forbidden':
      return t('admin.errors.selfAdminRoleRemovalForbidden')
    case 'last_active_administrator_forbidden':
      return t('admin.errors.lastActiveAdministratorForbidden')
    case 'acting_user_not_active_administrator':
      return t('admin.errors.actingUserNotActiveAdministrator')
    case 'resource_not_found':
      return t('admin.errors.resourceNotFound')
    case 'password_change_required':
      return t('admin.errors.passwordChangeRequired')
    case 'forbidden':
      return t('admin.errors.forbidden')
    case 'validation_error':
      return t('admin.errors.validationError')
    case 'authentication_required':
      return t('admin.errors.authenticationRequired')
    case 'network_error':
      return t('admin.errors.networkError')
    case 'unexpected':
      return t('admin.errors.unexpected')
    case null:
      return null
  }
}

function submit(): void {
  hasSubmitted.value = true
  if (displayNameError.value !== undefined || !hasChanges.value || props.isSubmitting) {
    return
  }
  if (isDeactivation.value) {
    isDeactivationConfirmationOpen.value = true
    return
  }
  emit('save', updateCommand.value)
}

function confirmDeactivation(): void {
  isDeactivationConfirmationOpen.value = false
  emit('save', updateCommand.value)
}

watch(() => props.account, resetDraft)
</script>

<template>
  <section class="admin-user-edit" :aria-labelledby="`admin-user-edit-${account.id}`">
    <h2 :id="`admin-user-edit-${account.id}`">
      {{ t('admin.editing.title', { username: account.username }) }}
    </h2>
    <form novalidate class="admin-user-edit-form" @submit.prevent="submit">
      <AppTextField
        :id="`admin-user-edit-username-${account.id}`"
        :model-value="account.username"
        name="username"
        :label="t('admin.editing.username')"
        readonly
      />
      <AppTextField
        :id="`admin-user-edit-display-name-${account.id}`"
        v-model="displayName"
        name="display_name"
        :label="t('admin.editing.displayName')"
        autocomplete="name"
        required
        :maxlength="200"
        :error-message="displayNameError"
      />
      <fieldset class="admin-user-edit-roles">
        <legend>{{ t('admin.editing.roles') }}</legend>
        <p>{{ t('admin.editing.rolesHint') }}</p>
        <div
          v-for="role in ['admin', 'operator'] as const"
          :key="role"
          class="admin-user-role-option"
        >
          <input
            :id="`admin-user-edit-role-${account.id}-${role}`"
            v-model="roles"
            type="checkbox"
            :value="role"
            :disabled="isCurrentAccount && role === 'admin'"
            :aria-describedby="
              isCurrentAccount && role === 'admin'
                ? `admin-user-edit-self-admin-${account.id}`
                : undefined
            "
          />
          <label :for="`admin-user-edit-role-${account.id}-${role}`">
            {{ t(`admin.roles.${role}`) }}
          </label>
        </div>
        <p v-if="isCurrentAccount" :id="`admin-user-edit-self-admin-${account.id}`">
          {{ t('admin.editing.selfAdminRoleLocked') }}
        </p>
      </fieldset>
      <div class="admin-user-edit-active">
        <input
          :id="`admin-user-edit-active-${account.id}`"
          v-model="isActive"
          type="checkbox"
          :disabled="isCurrentAccount"
          :aria-describedby="
            isCurrentAccount ? `admin-user-edit-self-active-${account.id}` : undefined
          "
        />
        <label :for="`admin-user-edit-active-${account.id}`">{{ t('admin.editing.active') }}</label>
        <p v-if="isCurrentAccount" :id="`admin-user-edit-self-active-${account.id}`">
          {{ t('admin.editing.selfDeactivationLocked') }}
        </p>
      </div>
      <p v-if="errorMessage(error)" role="alert" class="admin-user-edit-error">
        {{ errorMessage(error) }}
      </p>
      <div class="admin-user-edit-actions">
        <AppButton type="button" variant="ghost" :disabled="isSubmitting" @click="emit('cancel')">
          {{ t('admin.editing.cancel') }}
        </AppButton>
        <AppButton type="submit" :disabled="isSubmitting || !hasChanges">
          {{ isSubmitting ? t('admin.editing.submitting') : t('admin.editing.save') }}
        </AppButton>
      </div>
    </form>

    <Dialog
      :open="isDeactivationConfirmationOpen"
      class="admin-user-deactivation"
      @close="isDeactivationConfirmationOpen = false"
    >
      <div class="admin-user-deactivation-backdrop" aria-hidden="true" />
      <div class="admin-user-deactivation-frame">
        <DialogPanel class="admin-user-deactivation-panel">
          <DialogTitle class="admin-user-deactivation-title">
            {{ t('admin.deactivation.title') }}
          </DialogTitle>
          <p>{{ t('admin.deactivation.description') }}</p>
          <p>{{ t('admin.deactivation.sessions') }}</p>
          <div class="admin-user-deactivation-actions">
            <AppButton
              type="button"
              variant="ghost"
              @click="isDeactivationConfirmationOpen = false"
            >
              {{ t('admin.deactivation.cancel') }}
            </AppButton>
            <AppButton type="button" tone="destructive" @click="confirmDeactivation">
              {{ t('admin.deactivation.confirm') }}
            </AppButton>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  </section>
</template>

<style scoped>
.admin-user-edit {
  min-width: 0;
  overflow-wrap: anywhere;
  padding: var(--space-4) var(--page-gutter);
  background: var(--surface-1);
}

.admin-user-edit h2 {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.admin-user-edit-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.admin-user-edit-roles,
.admin-user-edit-active {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: 0;
}

.admin-user-edit-roles legend,
.admin-user-edit-active label {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

.admin-user-edit-roles > p,
.admin-user-edit-active p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.admin-user-role-option {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.admin-user-edit-active {
  grid-column: 1 / -1;
}

.admin-user-edit-active input {
  grid-row: 1;
  align-self: center;
}

.admin-user-edit-active label {
  grid-row: 1;
  grid-column: 2;
}

.admin-user-edit-active p {
  grid-column: 1 / -1;
}

.admin-user-edit-error {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--critical-text);
}

.admin-user-edit-actions {
  display: flex;
  grid-column: 1 / -1;
  justify-content: flex-end;
  gap: var(--space-3);
}

.admin-user-deactivation-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
}

.admin-user-deactivation-frame {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4) var(--page-gutter);
}

.admin-user-deactivation-panel {
  width: 100%;
  max-width: 28rem;
  padding: var(--space-6) var(--page-gutter);
  border-radius: var(--radius-modal);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.admin-user-deactivation-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
}

.admin-user-deactivation-panel p {
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
}

.admin-user-deactivation-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-5);
}

@media (max-width: 40rem) {
  .admin-user-edit-form {
    grid-template-columns: 1fr;
  }
}
</style>
