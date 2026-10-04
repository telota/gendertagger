import { useInfiniteQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, watch, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useDebouncedValue } from '@/composables/useDebouncedValue'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import {
  clearAdminTeamQueries,
  adminTeamsQueryKey,
  adminTeamRosterQueryKey,
} from '@/composables/resourceQueries'

export type TeamSummary = components['schemas']['TeamSummary']
export type TeamMember = components['schemas']['TeamMember']

const SEARCH_DEBOUNCE_MS = 300

/**
 * Global-administrator team and direct-roster discovery. Each cursor sequence is bound to the acting
 * principal and the exact server-side search tuple; cancellation prevents obsolete searches from completing.
 */
export function useAdminTeams(
  principalId: Readonly<Ref<string | null>>,
  canAccessAdmin: Readonly<Ref<boolean>>,
  teamSearchInput: Ref<string>,
  selectedTeamId: Readonly<Ref<string | null>>,
  rosterSearchInput: Ref<string>,
) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const teamSearch = useDebouncedValue(teamSearchInput, SEARCH_DEBOUNCE_MS)
  const rosterSearch = useDebouncedValue(rosterSearchInput, SEARCH_DEBOUNCE_MS)
  const canLoadTeams = computed(() => canAccessAdmin.value && principalId.value !== null)
  const canLoadRoster = computed(() => canLoadTeams.value && selectedTeamId.value !== null)

  const teamsQuery = useInfiniteQuery({
    queryKey: computed(() =>
      adminTeamsQueryKey(principalId.value ?? 'anonymous', teamSearch.value.trim()),
    ),
    queryFn: ({ pageParam, signal, queryKey }) => {
      const [, , , requestedSearch] = queryKey
      return unwrap(
        client.GET('/api/v1/admin/teams', {
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
    enabled: canLoadTeams,
  })

  const rosterQuery = useInfiniteQuery({
    queryKey: computed(() =>
      adminTeamRosterQueryKey(
        principalId.value ?? 'anonymous',
        selectedTeamId.value ?? 'unselected',
        rosterSearch.value.trim(),
      ),
    ),
    queryFn: ({ pageParam, signal, queryKey }) => {
      const [, , , requestedTeamId, requestedSearch] = queryKey
      return unwrap(
        client.GET('/api/v1/admin/teams/{team_id}/members', {
          params: {
            path: { team_id: requestedTeamId },
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
    enabled: canLoadRoster,
  })

  function clearPrivateData(principal = principalId.value): void {
    if (principal !== null) clearAdminTeamQueries(queryClient, principal)
  }

  function cancelTeamSearch(previousSearch: string): void {
    const principal = principalId.value
    if (principal !== null) {
      void queryClient.cancelQueries({
        queryKey: adminTeamsQueryKey(principal, previousSearch.trim()),
      })
    }
  }

  function cancelRosterSearch(teamId: string, previousSearch: string): void {
    const principal = principalId.value
    if (principal !== null) {
      void queryClient.cancelQueries({
        queryKey: adminTeamRosterQueryKey(principal, teamId, previousSearch.trim()),
      })
    }
  }

  watch(teamSearch, (nextSearch, previousSearch) => {
    if (nextSearch !== previousSearch) cancelTeamSearch(previousSearch)
  })

  watch(rosterSearch, (nextSearch, previousSearch) => {
    const teamId = selectedTeamId.value
    if (teamId !== null && nextSearch !== previousSearch) {
      cancelRosterSearch(teamId, previousSearch)
    }
  })

  watch(selectedTeamId, (nextTeamId, previousTeamId) => {
    if (nextTeamId !== previousTeamId && previousTeamId !== null) {
      cancelRosterSearch(previousTeamId, rosterSearch.value)
    }
  })

  watch(principalId, (nextPrincipal, previousPrincipal) => {
    if (nextPrincipal !== previousPrincipal && previousPrincipal !== null) {
      clearAdminTeamQueries(queryClient, previousPrincipal)
    }
  })

  watch(canAccessAdmin, (canAccess) => {
    if (!canAccess) clearPrivateData()
  })

  onScopeDispose(() => {
    clearPrivateData()
  })

  return {
    teamsQuery,
    rosterQuery,
    teamSearch,
    rosterSearch,
    clearPrivateData,
  }
}
