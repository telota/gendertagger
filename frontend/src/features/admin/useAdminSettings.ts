import { useQuery, useQueryClient, type QueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, watch, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

export type AdminSettings = components['schemas']['AdminSettings']

const ADMIN_SETTINGS_QUERY_ROOT = ['admin', 'settings'] as const

export function adminSettingsQueryKey(principalId: string) {
  return [...ADMIN_SETTINGS_QUERY_ROOT, principalId] as const
}

function clearAdminSettingsQuery(queryClient: QueryClient, principalId: string): void {
  const queryKey = adminSettingsQueryKey(principalId)
  void queryClient.cancelQueries({ queryKey })
  queryClient.removeQueries({ queryKey })
}

/**
 * `GET /admin/settings`, scoped to the eligible administrator that requested it. The response contains
 * administrative metadata and remains private query state even though effective branding is public elsewhere.
 */
export function useAdminSettings(
  principalId: Readonly<Ref<string | null>>,
  canAccessAdmin: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const enabled = computed(() => canAccessAdmin.value && principalId.value !== null)
  const query = useQuery({
    queryKey: computed(() => adminSettingsQueryKey(principalId.value ?? 'anonymous')),
    queryFn: () => unwrap(client.GET('/api/v1/admin/settings')),
    enabled,
  })

  function clearPrivateData(principal = principalId.value): void {
    if (principal !== null) clearAdminSettingsQuery(queryClient, principal)
  }

  watch(principalId, (nextPrincipal, previousPrincipal) => {
    if (nextPrincipal !== previousPrincipal && previousPrincipal !== null) {
      clearAdminSettingsQuery(queryClient, previousPrincipal)
    }
  })

  watch(canAccessAdmin, (canAccess) => {
    if (!canAccess) clearPrivateData()
  })

  onScopeDispose(() => {
    clearPrivateData()
  })

  return { query, clearPrivateData }
}
