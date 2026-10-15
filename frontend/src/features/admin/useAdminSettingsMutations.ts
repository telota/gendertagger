import { useQueryClient } from '@tanstack/vue-query'
import { onScopeDispose, ref, watch, type Ref } from 'vue'

import { ApiError, unwrap, type components } from '@/api'
import { refreshPublicBranding } from '@/composables/useBranding'
import { useApiClient } from '@/composables/useApiClient'

import { adminSettingsQueryKey, type AdminSettings } from './useAdminSettings'

export type AdminSettingsUpdateCommand = components['schemas']['AdminSettingsUpdate']
export type AdminSettingsResetCommand = components['schemas']['AdminSettingsReset']
export type AggregationSettingsUpdateCommand = components['schemas']['AggregationSettingsUpdate']
export type AdminSettingsMutationError =
  | 'settings_revision_conflict'
  | 'settings_unavailable'
  | 'validation_error'
  | 'authentication_required'
  | 'password_change_required'
  | 'forbidden'
  | 'network_error'
  | 'unexpected'

export type AdminSettingsMutationResult =
  | { status: 'success'; settings: AdminSettings; publicRefreshFailed: boolean }
  | { status: 'conflict'; latest: AdminSettings | null }
  | { status: 'failure'; error: AdminSettingsMutationError }
  | { status: 'discarded' }

function mutationErrorCode(error: unknown): AdminSettingsMutationError {
  if (!(error instanceof ApiError)) return 'unexpected'

  switch (error.code) {
    case 'settings_revision_conflict':
    case 'settings_unavailable':
    case 'validation_error':
    case 'authentication_required':
    case 'password_change_required':
    case 'forbidden':
    case 'network_error':
      return error.code
    default:
      return 'unexpected'
  }
}

/**
 * Serialized administrative settings writes. Results are discarded when the owning administrator or view
 * changes, and a confirmed write refreshes only the public `BrandingInfo` cache, never private metadata.
 */
export function useAdminSettingsMutations(
  principalId: Readonly<Ref<string | null>>,
  canAccessAdmin: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const isSubmitting = ref(false)
  let privateStateEpoch = 0

  function isCurrentPrincipal(principal: string, requestEpoch: number): boolean {
    return (
      privateStateEpoch === requestEpoch && canAccessAdmin.value && principalId.value === principal
    )
  }

  function clearPrivateState(): void {
    privateStateEpoch += 1
    isSubmitting.value = false
  }

  async function loadLatest(
    principal: string,
    requestEpoch: number,
  ): Promise<AdminSettings | null> {
    try {
      const latest = await unwrap(client.GET('/api/v1/admin/settings'))
      if (isCurrentPrincipal(principal, requestEpoch)) {
        queryClient.setQueryData(adminSettingsQueryKey(principal), latest)
        return latest
      }
    } catch {
      // The stale draft remains available for explicit reconciliation once the read can succeed.
    }
    return null
  }

  async function refreshBranding(): Promise<boolean> {
    try {
      await refreshPublicBranding(queryClient, client)
      return true
    } catch {
      return false
    }
  }

  async function apply(
    request: () => Promise<AdminSettings>,
  ): Promise<AdminSettingsMutationResult> {
    const principal = principalId.value
    const requestEpoch = privateStateEpoch
    if (principal === null || !isCurrentPrincipal(principal, requestEpoch) || isSubmitting.value) {
      return { status: 'discarded' }
    }

    isSubmitting.value = true
    try {
      const settings = await request()
      if (!isCurrentPrincipal(principal, requestEpoch)) return { status: 'discarded' }

      queryClient.setQueryData(adminSettingsQueryKey(principal), settings)
      const publicRefreshFailed = !(await refreshBranding())
      if (!isCurrentPrincipal(principal, requestEpoch)) return { status: 'discarded' }
      return { status: 'success', settings, publicRefreshFailed }
    } catch (error) {
      if (!isCurrentPrincipal(principal, requestEpoch)) return { status: 'discarded' }

      const code = mutationErrorCode(error)
      if (code === 'settings_revision_conflict') {
        const latest = await loadLatest(principal, requestEpoch)
        return isCurrentPrincipal(principal, requestEpoch)
          ? { status: 'conflict', latest }
          : { status: 'discarded' }
      }
      return { status: 'failure', error: code }
    } finally {
      if (isCurrentPrincipal(principal, requestEpoch)) isSubmitting.value = false
    }
  }

  function update(command: AdminSettingsUpdateCommand): Promise<AdminSettingsMutationResult> {
    return apply(() => unwrap(client.PATCH('/api/v1/admin/settings', { body: command })))
  }

  function reset(command: AdminSettingsResetCommand): Promise<AdminSettingsMutationResult> {
    return apply(() => unwrap(client.POST('/api/v1/admin/settings/reset', { body: command })))
  }

  function updateAggregationSettings(
    command: AggregationSettingsUpdateCommand,
  ): Promise<AdminSettingsMutationResult> {
    return apply(() =>
      unwrap(client.PATCH('/api/v1/admin/settings/aggregation', { body: command })),
    )
  }

  watch([principalId, canAccessAdmin], clearPrivateState)
  onScopeDispose(clearPrivateState)

  return {
    isSubmitting,
    update,
    reset,
    updateAggregationSettings,
    refreshBranding,
    clearPrivateState,
  }
}
