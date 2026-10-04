<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'

import type { AdminUserMutationError } from './useAdminUserMutations'

type GlobalRole = components['schemas']['GlobalRole']
const GLOBAL_ROLES: readonly GlobalRole[] = ['admin', 'operator']

const props = defineProps<{
  isSubmitting: boolean
  error: AdminUserMutationError | null
  temporaryPassword: string | null
}>()

const emit = defineEmits<{
  create: [command: components['schemas']['AdminUserCreate']]
  dismissTemporaryPassword: []
}>()

const { t } = useI18n()
const username = ref('')
const displayName = ref('')
const roles = ref<GlobalRole[]>([])
const hasSubmitted = ref(false)
const usernamePattern = /^[a-z0-9][a-z0-9._-]{0,62}[a-z0-9]$/

function resetDraft(): void {
  username.value = ''
  displayName.value = ''
  roles.value = []
  hasSubmitted.value = false
}

useDraftRegistration(
  () => username.value !== '' || displayName.value !== '' || roles.value.length > 0,
  resetDraft,
)

const normalizedUsername = computed(() => username.value.trim().toLowerCase())
const usernameError = computed(() => {
  if (!hasSubmitted.value || usernamePattern.test(normalizedUsername.value)) return undefined
  return t('admin.creation.validation.username')
})
const displayNameError = computed(() => {
  if (!hasSubmitted.value) return undefined
  if (displayName.value.trim() === '') return t('admin.creation.validation.displayNameRequired')
  if (displayName.value.length > 200) return t('admin.creation.validation.displayNameLength')
  return undefined
})

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
  if (
    usernameError.value !== undefined ||
    displayNameError.value !== undefined ||
    props.isSubmitting
  ) {
    return
  }

  emit('create', {
    username: username.value,
    display_name: displayName.value,
    roles: [...roles.value],
  })
}

watch(
  () => props.temporaryPassword,
  (password) => {
    if (password === null) return
    resetDraft()
  },
)
</script>

<template>
  <section class="admin-user-creation app-card" aria-labelledby="admin-user-creation-heading">
    <h2 id="admin-user-creation-heading">{{ t('admin.creation.title') }}</h2>
    <p>{{ t('admin.creation.description') }}</p>

    <form novalidate class="admin-user-creation-form" @submit.prevent="submit">
      <AppTextField
        id="admin-user-create-username"
        v-model="username"
        name="username"
        :label="t('admin.creation.username')"
        autocomplete="username"
        required
        :error-message="usernameError"
      />
      <AppTextField
        id="admin-user-create-display-name"
        v-model="displayName"
        name="display_name"
        :label="t('admin.creation.displayName')"
        autocomplete="name"
        required
        :maxlength="200"
        :error-message="displayNameError"
      />
      <fieldset class="admin-user-creation-roles">
        <legend>{{ t('admin.creation.roles') }}</legend>
        <p>{{ t('admin.creation.rolesHint') }}</p>
        <div class="admin-user-role-options">
          <div v-for="role in GLOBAL_ROLES" :key="role" class="admin-user-role-option">
            <input
              :id="`admin-user-create-role-${role}`"
              v-model="roles"
              type="checkbox"
              :value="role"
            />
            <label :for="`admin-user-create-role-${role}`">{{ t(`admin.roles.${role}`) }}</label>
          </div>
        </div>
      </fieldset>
      <p v-if="errorMessage(error)" role="alert" class="admin-user-creation-error">
        {{ errorMessage(error) }}
      </p>
      <div class="admin-user-creation-actions app-form-actions">
        <AppButton type="submit" :disabled="isSubmitting">
          {{ isSubmitting ? t('admin.creation.submitting') : t('admin.creation.submit') }}
        </AppButton>
      </div>
    </form>

    <section
      v-if="temporaryPassword"
      class="admin-user-temporary-password"
      aria-labelledby="admin-user-temporary-password-heading"
      role="status"
    >
      <h3 id="admin-user-temporary-password-heading">
        {{ t('admin.creation.successTitle') }}
      </h3>
      <p>{{ t('admin.creation.successDescription') }}</p>
      <AppTextField
        id="admin-user-temporary-password"
        class="admin-user-password-field"
        :label="t('admin.creation.temporaryPassword')"
        readonly
        :model-value="temporaryPassword"
        aria-describedby="admin-user-temporary-password-help"
      />
      <p id="admin-user-temporary-password-help">
        {{ t('admin.creation.temporaryPasswordHelp') }}
      </p>
      <AppButton type="button" variant="ghost" @click="emit('dismissTemporaryPassword')">
        {{ t('admin.creation.dismissTemporaryPassword') }}
      </AppButton>
    </section>
  </section>
</template>

<style scoped>
.admin-user-creation {
  container: admin-user-creation / inline-size;
  min-width: 0;
  overflow-wrap: anywhere;
}

.admin-user-creation h2,
.admin-user-temporary-password h3 {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.admin-user-creation > p,
.admin-user-creation-roles > p,
.admin-user-temporary-password > p {
  margin: 0;
  max-inline-size: 65ch;
  color: var(--text-secondary);
}

.admin-user-creation-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-4);
  margin-top: var(--space-5);
}

/* Username and display name side by side once the card has room, like the project form. */
@container admin-user-creation (min-width: 36rem) {
  .admin-user-creation-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .admin-user-creation-roles,
  .admin-user-creation-error {
    grid-column: 1 / -1;
  }
}

.admin-user-creation-roles {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: 0;
}

.admin-user-creation-roles legend {
  padding: 0;
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

.admin-user-creation-roles > p {
  font-size: var(--font-size-small);
}

.admin-user-role-options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-6);
}

.admin-user-role-option {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.admin-user-creation-error {
  margin: 0;
  color: var(--critical-text);
}

.admin-user-temporary-password {
  display: grid;
  gap: var(--space-3);
  margin-top: var(--space-6);
  padding-top: var(--space-5);
  border-top: 1px solid var(--grid);
}

.admin-user-password-field {
  --field-gap: var(--space-3);
  --field-label-size: inherit;
  --field-label-color: var(--text-primary);
  --field-control-width: 100%;
  --field-control-max-width: 28rem;
  --field-control-background: var(--surface-1);
}
</style>
