import { useQueryClient } from '@tanstack/vue-query'
import { onScopeDispose, ref, watch, type Ref } from 'vue'

import { ApiError, unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

import { invalidateAdminUserQueries } from './useAdminUserDirectory'

export type AdminUserCreateCommand = components['schemas']['AdminUserCreate']
export type AdminUserUpdateCommand = components['schemas']['AdminUserUpdate']
export type AdminUser = components['schemas']['AdminUser']

export interface PasswordResetDisclosure {
  operation: 'password_reset'
  targetUserId: string
  targetUsername: string
  temporaryPassword: string
}

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

export type AdminUserSecurityError =
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

function securityErrorCode(error: unknown): AdminUserSecurityError {
  const code = mutationErrorCode(error)
  switch (code) {
    case 'resource_not_found':
    case 'password_change_required':
    case 'forbidden':
    case 'validation_error':
    case 'authentication_required':
    case 'network_error':
      return code
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
  const resetDisclosure = ref<PasswordResetDisclosure | null>(null)
  const isCreating = ref(false)
  const isUpdating = ref(false)
  const isPerformingSecurityAction = ref(false)
  const createError = ref<AdminUserMutationError | null>(null)
  const updateError = ref<AdminUserMutationError | null>(null)
  const securityError = ref<AdminUserSecurityError | null>(null)
  const securityTargetUserId = ref<string | null>(null)
  const resetDirectoryRefreshFailed = ref(false)
  // An in-flight write must not repopulate private state after its view, principal, or access changes.
  let privateStateEpoch = 0

  function isCurrentPrincipal(principal: string, requestEpoch: number): boolean {
    return (
      privateStateEpoch === requestEpoch && canAccessAdmin.value && principalId.value === principal
    )
  }

  function clearPrivateState(): void {
    privateStateEpoch += 1
    temporaryPassword.value = null
    resetDisclosure.value = null
    isCreating.value = false
    isUpdating.value = false
    isPerformingSecurityAction.value = false
    createError.value = null
    updateError.value = null
    securityError.value = null
    securityTargetUserId.value = null
    resetDirectoryRefreshFailed.value = false
  }

  async function refreshDirectory(
    principal: string,
    requestEpoch: number,
    reportResetRefreshFailure = false,
  ): Promise<void> {
    // A committed write remains successful even when the resulting refetch fails. In particular, retain
    // the one-time reset disclosure so the administrator can still record the replacement credential.
    try {
      await invalidateAdminUserQueries(queryClient, principal, reportResetRefreshFailure)
    } catch {
      if (reportResetRefreshFailure && isCurrentPrincipal(principal, requestEpoch)) {
        resetDirectoryRefreshFailed.value = true
      }
    }
  }

  async function create(command: AdminUserCreateCommand): Promise<boolean> {
    const principal = principalId.value
    const requestEpoch = privateStateEpoch
    if (principal === null || !isCurrentPrincipal(principal, requestEpoch) || isCreating.value) {
      return false
    }

    isCreating.value = true
    createError.value = null
    temporaryPassword.value = null
    try {
      const result = await unwrap(client.POST('/api/v1/admin/users', { body: command }))
      if (!isCurrentPrincipal(principal, requestEpoch)) return false

      temporaryPassword.value = result.temporary_password
      void refreshDirectory(principal, requestEpoch)
      return true
    } catch (error) {
      if (isCurrentPrincipal(principal, requestEpoch)) {
        createError.value = mutationErrorCode(error)
      }
      return false
    } finally {
      if (isCurrentPrincipal(principal, requestEpoch)) {
        isCreating.value = false
      }
    }
  }

  async function update(
    userId: string,
    command: AdminUserUpdateCommand,
  ): Promise<AdminUser | null> {
    const principal = principalId.value
    const requestEpoch = privateStateEpoch
    if (principal === null || !isCurrentPrincipal(principal, requestEpoch) || isUpdating.value) {
      return null
    }

    isUpdating.value = true
    updateError.value = null
    try {
      const account = await unwrap(
        client.PATCH('/api/v1/admin/users/{user_id}', {
          params: { path: { user_id: userId } },
          body: command,
        }),
      )
      if (!isCurrentPrincipal(principal, requestEpoch)) return null

      void refreshDirectory(principal, requestEpoch)
      return account
    } catch (error) {
      if (isCurrentPrincipal(principal, requestEpoch)) {
        updateError.value = mutationErrorCode(error)
      }
      return null
    } finally {
      if (isCurrentPrincipal(principal, requestEpoch)) {
        isUpdating.value = false
      }
    }
  }

  async function resetPassword(account: Pick<AdminUser, 'id' | 'username'>): Promise<boolean> {
    const principal = principalId.value
    const requestEpoch = privateStateEpoch
    if (
      principal === null ||
      !isCurrentPrincipal(principal, requestEpoch) ||
      isPerformingSecurityAction.value
    ) {
      return false
    }

    isPerformingSecurityAction.value = true
    securityError.value = null
    securityTargetUserId.value = account.id
    resetDisclosure.value = null
    resetDirectoryRefreshFailed.value = false
    try {
      const result = await unwrap(
        client.POST('/api/v1/admin/users/{user_id}/reset-password', {
          params: { path: { user_id: account.id } },
        }),
      )
      if (!isCurrentPrincipal(principal, requestEpoch)) return false

      resetDisclosure.value = {
        operation: 'password_reset',
        targetUserId: account.id,
        targetUsername: account.username,
        temporaryPassword: result.temporary_password,
      }
      void refreshDirectory(principal, requestEpoch, true)
      return true
    } catch (error) {
      if (isCurrentPrincipal(principal, requestEpoch)) {
        securityError.value = securityErrorCode(error)
      }
      return false
    } finally {
      if (isCurrentPrincipal(principal, requestEpoch)) {
        isPerformingSecurityAction.value = false
      }
    }
  }

  async function revokeSessions(account: Pick<AdminUser, 'id' | 'username'>): Promise<boolean> {
    const principal = principalId.value
    const requestEpoch = privateStateEpoch
    if (
      principal === null ||
      !isCurrentPrincipal(principal, requestEpoch) ||
      isPerformingSecurityAction.value
    ) {
      return false
    }

    isPerformingSecurityAction.value = true
    securityError.value = null
    securityTargetUserId.value = account.id
    resetDisclosure.value = null
    resetDirectoryRefreshFailed.value = false
    try {
      await unwrap(
        client.POST('/api/v1/admin/users/{user_id}/revoke-sessions', {
          params: { path: { user_id: account.id } },
        }),
      )
      if (!isCurrentPrincipal(principal, requestEpoch)) return false

      return true
    } catch (error) {
      if (isCurrentPrincipal(principal, requestEpoch)) {
        securityError.value = securityErrorCode(error)
      }
      return false
    } finally {
      if (isCurrentPrincipal(principal, requestEpoch)) {
        isPerformingSecurityAction.value = false
      }
    }
  }

  function clearTemporaryPassword(): void {
    temporaryPassword.value = null
  }

  function clearResetDisclosure(): void {
    resetDisclosure.value = null
    resetDirectoryRefreshFailed.value = false
  }

  watch([principalId, canAccessAdmin], () => {
    clearPrivateState()
  })

  onScopeDispose(clearPrivateState)

  return {
    temporaryPassword,
    resetDisclosure,
    isCreating,
    isUpdating,
    isPerformingSecurityAction,
    createError,
    updateError,
    securityError,
    securityTargetUserId,
    resetDirectoryRefreshFailed,
    create,
    update,
    resetPassword,
    revokeSessions,
    clearPrivateState,
    clearTemporaryPassword,
    clearResetDisclosure,
    isAdminAccessError: (error: AdminUserMutationError | null) =>
      error !== null && ADMIN_ACCESS_ERROR_CODES[error] === true,
  }
}
