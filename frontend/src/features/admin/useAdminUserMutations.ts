import { useQueryClient } from '@tanstack/vue-query'
import { onScopeDispose, ref, watch, type Ref } from 'vue'

import { ApiError, unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

import { invalidateAdminUserQueries } from './useAdminUserDirectory'

export type AdminUserCreateCommand = components['schemas']['AdminUserCreate']
export type AdminUserUpdateCommand = components['schemas']['AdminUserUpdate']
export type AdminUser = components['schemas']['AdminUser']

export type AdminUserMutationError =
  | 'username_conflict'
  | 'self_deactivation_forbidden'
  | 'self_admin_role_removal_forbidden'
  | 'last_active_administrator_forbidden'
  | 'acting_user_not_active_administrator'
  | 'resource_not_found'
  | 'password_change_required'
  | 'forbidden'
  | 'validation_error'
  | 'authentication_required'
  | 'network_error'
  | 'unexpected'

const ADMIN_ACCESS_ERROR_CODES: Record<string, true> = {
  acting_user_not_active_administrator: true,
  password_change_required: true,
  forbidden: true,
}

function mutationErrorCode(error: unknown): AdminUserMutationError {
  if (!(error instanceof ApiError)) return 'unexpected'

  switch (error.code) {
    case 'username_conflict':
    case 'self_deactivation_forbidden':
    case 'self_admin_role_removal_forbidden':
    case 'last_active_administrator_forbidden':
    case 'acting_user_not_active_administrator':
    case 'resource_not_found':
    case 'password_change_required':
    case 'forbidden':
    case 'validation_error':
    case 'authentication_required':
    case 'network_error':
      return error.code
    default:
      return 'unexpected'
  }
}

/**
 * Imperative administrative writes. The generated temporary password remains only in this composable's
 * component-scoped ref, never in a mutation cache or shared state.
 */
export function useAdminUserMutations(
  principalId: Readonly<Ref<string | null>>,
  canAccessAdmin: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const temporaryPassword = ref<string | null>(null)
  const isCreating = ref(false)
  const isUpdating = ref(false)
  const createError = ref<AdminUserMutationError | null>(null)
  const updateError = ref<AdminUserMutationError | null>(null)

  function isCurrentPrincipal(principal: string): boolean {
    return canAccessAdmin.value && principalId.value === principal
  }

  function clearPrivateState(): void {
    temporaryPassword.value = null
    createError.value = null
    updateError.value = null
  }

  async function refreshDirectory(principal: string): Promise<void> {
    // This is deliberately detached from write success: a committed create must not lose its sole password
    // disclosure just because a subsequent directory read fails.
    await invalidateAdminUserQueries(queryClient, principal)
  }

  async function create(command: AdminUserCreateCommand): Promise<boolean> {
    const principal = principalId.value
    if (principal === null || !isCurrentPrincipal(principal) || isCreating.value) return false

    isCreating.value = true
    createError.value = null
    temporaryPassword.value = null
    try {
      const result = await unwrap(client.POST('/api/v1/admin/users', { body: command }))
      if (!isCurrentPrincipal(principal)) return false

      temporaryPassword.value = result.temporary_password
      void refreshDirectory(principal)
      return true
    } catch (error) {
      if (isCurrentPrincipal(principal)) {
        createError.value = mutationErrorCode(error)
      }
      return false
    } finally {
      isCreating.value = false
    }
  }

  async function update(
    userId: string,
    command: AdminUserUpdateCommand,
  ): Promise<AdminUser | null> {
    const principal = principalId.value
    if (principal === null || !isCurrentPrincipal(principal) || isUpdating.value) return null

    isUpdating.value = true
    updateError.value = null
    try {
      const account = await unwrap(
        client.PATCH('/api/v1/admin/users/{user_id}', {
          params: { path: { user_id: userId } },
          body: command,
        }),
      )
      if (!isCurrentPrincipal(principal)) return null

      void refreshDirectory(principal)
      return account
    } catch (error) {
      if (isCurrentPrincipal(principal)) {
        updateError.value = mutationErrorCode(error)
      }
      return null
    } finally {
      isUpdating.value = false
    }
  }

  function clearTemporaryPassword(): void {
    temporaryPassword.value = null
  }

  watch([principalId, canAccessAdmin], () => {
    clearPrivateState()
  })

  onScopeDispose(clearPrivateState)

  return {
    temporaryPassword,
    isCreating,
    isUpdating,
    createError,
    updateError,
    create,
    update,
    clearPrivateState,
    clearTemporaryPassword,
    isAdminAccessError: (error: AdminUserMutationError | null) =>
      error !== null && ADMIN_ACCESS_ERROR_CODES[error] === true,
  }
}
