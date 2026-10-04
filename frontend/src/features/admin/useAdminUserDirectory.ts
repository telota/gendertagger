import { useInfiniteQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, watch, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useDebouncedValue } from '@/composables/useDebouncedValue'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import { clearAdminUserQueries, adminUsersQueryKey } from '@/composables/resourceQueries'

export type AdminUser = components['schemas']['AdminUser']

const SEARCH_DEBOUNCE_MS = 300

/**
 * `GET /admin/users`, scoped to one administrator and one server-side search tuple. Cursors stay
 * inside TanStack Query pages under that exact key; neither rows nor their order are transformed.
 */
export function useAdminUserDirectory(
  principalId: Readonly<Ref<string | null>>,
  canAccessAdmin: Readonly<Ref<boolean>>,
  searchInput: Ref<string>,
) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const search = useDebouncedValue(searchInput, SEARCH_DEBOUNCE_MS)
  const enabled = computed(() => canAccessAdmin.value && principalId.value !== null)

  const query = useInfiniteQuery({
    queryKey: computed(() =>
      adminUsersQueryKey(principalId.value ?? 'anonymous', search.value.trim()),
    ),
    queryFn: ({ pageParam, signal, queryKey }) => {
      const [, , , requestedSearch] = queryKey
      return unwrap(
        client.GET('/api/v1/admin/users', {
          params: {
            query: {
              query: requestedSearch === '' ? null : requestedSearch,
              cursor: pageParam,
            },
          },
          signal,
        }),
      )
    },
    ...cursorQueryOptions,
    enabled,
  })

  function clearPrivateData(principal = principalId.value): void {
    if (principal !== null) clearAdminUserQueries(queryClient, principal)
  }

  watch(search, (nextSearch, previousSearch) => {
    const principal = principalId.value
    if (principal !== null && nextSearch !== previousSearch) {
      void queryClient.cancelQueries({
        queryKey: adminUsersQueryKey(principal, previousSearch.trim()),
      })
    }
  })

  watch(principalId, (nextPrincipal, previousPrincipal) => {
    if (nextPrincipal !== previousPrincipal && previousPrincipal !== null) {
      clearAdminUserQueries(queryClient, previousPrincipal)
    }
  })

  watch(canAccessAdmin, (canAccess) => {
    if (!canAccess) clearPrivateData()
  })

  onScopeDispose(() => {
    clearPrivateData()
  })

  return { query, search, clearPrivateData }
}
