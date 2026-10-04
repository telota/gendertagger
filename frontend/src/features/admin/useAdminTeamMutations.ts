import { useQueryClient } from '@tanstack/vue-query'
import { onScopeDispose, ref, watch, type Ref } from 'vue'

import { ApiError, unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

import { invalidateAdminTeamQueries } from '@/composables/resourceQueries'

export type TeamCreateCommand = components['schemas']['TeamCreate']
export type TeamUpdateCommand = components['schemas']['TeamUpdate']
export type TeamMutationError =
  | 'team_slug_conflict'
  | 'team_not_empty'
  | 'team_in_use'
  | 'inactive_user'
  | 'manager_replacement_required'
  | 'team_membership_conflict'
  | 'resource_not_found'
  | 'password_change_required'
  | 'forbidden'
  | 'validation_error'
  | 'authentication_required'
  | 'network_error'
  | 'unexpected'

export type TeamMutationOperation = 'create' | 'rename' | 'delete' | 'addMember' | 'removeMember'

export interface TeamMutationNotice {
  operation: TeamMutationOperation
  teamId: string | null
  targetUserId: string | null
}

const ADMIN_ACCESS_ERROR_CODES: Record<string, true> = {
  password_change_required: true,
  forbidden: true,
}

function mutationErrorCode(error: unknown): TeamMutationError {
  if (!(error instanceof ApiError)) return 'unexpected'

  switch (error.code) {
    case 'team_slug_conflict':
    case 'team_not_empty':
    case 'team_in_use':
    case 'inactive_user':
    case 'manager_replacement_required':
    case 'team_membership_conflict':
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
 * Imperative administrative team writes. A write is never replayed after authentication recovery; the
 * principal, selected team, and target are captured before dispatch so obsolete responses cannot alter state.
 */
export function useAdminTeamMutations(
  principalId: Readonly<Ref<string | null>>,
  canAccessAdmin: Readonly<Ref<boolean>>,
  selectedTeamId: Readonly<Ref<string | null>>,
) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const isMutating = ref(false)
  const error = ref<TeamMutationError | null>(null)
  const errorNotice = ref<TeamMutationNotice | null>(null)
  const successNotice = ref<TeamMutationNotice | null>(null)
  const refreshFailedNotice = ref<TeamMutationNotice | null>(null)
  let privateStateEpoch = 0

  function isCurrent(principal: string, requestEpoch: number, teamId: string | null): boolean {
    return (
      privateStateEpoch === requestEpoch &&
      canAccessAdmin.value &&
      principalId.value === principal &&
      (teamId === null || selectedTeamId.value === teamId)
    )
  }

  function clearPrivateState(): void {
    privateStateEpoch += 1
    isMutating.value = false
    error.value = null
    errorNotice.value = null
    successNotice.value = null
    refreshFailedNotice.value = null
  }

  function clearScopedState(): void {
    privateStateEpoch += 1
    isMutating.value = false
    error.value = null
    errorNotice.value = null
  }

  async function refresh(
    principal: string,
    requestEpoch: number,
    notice: TeamMutationNotice,
  ): Promise<void> {
    try {
      await invalidateAdminTeamQueries(queryClient, principal, true)
    } catch {
      if (isCurrent(principal, requestEpoch, notice.teamId)) {
        refreshFailedNotice.value = notice
      }
    }
  }

  async function perform<T>(
    notice: TeamMutationNotice,
    request: () => Promise<T>,
  ): Promise<T | null> {
    const principal = principalId.value
    const requestEpoch = privateStateEpoch
    if (
      principal === null ||
      !isCurrent(principal, requestEpoch, notice.teamId) ||
      isMutating.value
    ) {
      return null
    }

    isMutating.value = true
    error.value = null
    errorNotice.value = null
    successNotice.value = null
    refreshFailedNotice.value = null
    try {
      const result = await request()
      if (!isCurrent(principal, requestEpoch, notice.teamId)) return null

      successNotice.value = notice
      void refresh(principal, requestEpoch, notice)
      return result
    } catch (requestError) {
      if (isCurrent(principal, requestEpoch, notice.teamId)) {
        error.value = mutationErrorCode(requestError)
        errorNotice.value = notice
      }
      return null
    } finally {
      if (isCurrent(principal, requestEpoch, notice.teamId)) {
        isMutating.value = false
      }
    }
  }

  function create(command: TeamCreateCommand) {
    return perform({ operation: 'create', teamId: null, targetUserId: null }, () =>
      unwrap(client.POST('/api/v1/admin/teams', { body: command })),
    )
  }

  function rename(teamId: string, command: TeamUpdateCommand) {
    return perform({ operation: 'rename', teamId, targetUserId: null }, () =>
      unwrap(
        client.PATCH('/api/v1/admin/teams/{team_id}', {
          params: { path: { team_id: teamId } },
          body: command,
        }),
      ),
    )
  }

  function deleteTeam(teamId: string) {
    return perform({ operation: 'delete', teamId, targetUserId: null }, () =>
      unwrap(
        client.DELETE('/api/v1/admin/teams/{team_id}', {
          params: { path: { team_id: teamId } },
        }),
      ),
    )
  }

  function addMember(teamId: string, userId: string) {
    return perform({ operation: 'addMember', teamId, targetUserId: userId }, () =>
      unwrap(
        client.POST('/api/v1/admin/teams/{team_id}/members', {
          params: { path: { team_id: teamId } },
          body: { user_id: userId },
        }),
      ),
    )
  }

  function removeMember(teamId: string, userId: string) {
    return perform({ operation: 'removeMember', teamId, targetUserId: userId }, () =>
      unwrap(
        client.DELETE('/api/v1/admin/teams/{team_id}/members/{user_id}', {
          params: { path: { team_id: teamId, user_id: userId } },
        }),
      ),
    )
  }

  watch([principalId, canAccessAdmin], clearPrivateState)
  watch(selectedTeamId, clearScopedState)
  onScopeDispose(clearPrivateState)

  return {
    isMutating,
    error,
    errorNotice,
    successNotice,
    refreshFailedNotice,
    create,
    rename,
    deleteTeam,
    addMember,
    removeMember,
    clearPrivateState,
    isAdminAccessError: (candidate: TeamMutationError | null) =>
      candidate !== null && ADMIN_ACCESS_ERROR_CODES[candidate] === true,
  }
}
