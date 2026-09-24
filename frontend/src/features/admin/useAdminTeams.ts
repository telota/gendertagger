import { useInfiniteQuery, useQueryClient, type QueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, watch, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useDebouncedValue } from '@/composables/useDebouncedValue'

export type TeamSummary = components['schemas']['TeamSummary']
export type TeamMember = components['schemas']['TeamMember']

const ADMIN_TEAMS_QUERY_ROOT = ['admin', 'teams'] as const
const ADMIN_TEAM_ROSTER_QUERY_ROOT = ['admin', 'team-members'] as const
const SEARCH_DEBOUNCE_MS = 300

export function adminTeamsQueryKey(principalId: string, search: string) {
  return [...ADMIN_TEAMS_QUERY_ROOT, principalId, search] as const
}

export function adminTeamRosterQueryKey(principalId: string, teamId: string, search: string) {
  return [...ADMIN_TEAM_ROSTER_QUERY_ROOT, principalId, teamId, search] as const
}

function clearAdminTeamQueries(queryClient: QueryClient, principalId: string): void {
  const teamQueryKey = [...ADMIN_TEAMS_QUERY_ROOT, principalId] as const
  const rosterQueryKey = [...ADMIN_TEAM_ROSTER_QUERY_ROOT, principalId] as const
  void queryClient.cancelQueries({ queryKey: teamQueryKey })
  void queryClient.cancelQueries({ queryKey: rosterQueryKey })
  queryClient.removeQueries({ queryKey: teamQueryKey })
  queryClient.removeQueries({ queryKey: rosterQueryKey })
}

export function invalidateAdminTeamQueries(
  queryClient: QueryClient,
  principalId: string,
  throwOnError = false,
): Promise<void> {
  return Promise.all([
    queryClient.invalidateQueries(
      { queryKey: [...ADMIN_TEAMS_QUERY_ROOT, principalId] },
      { throwOnError },
    ),
    queryClient.invalidateQueries(
      { queryKey: [...ADMIN_TEAM_ROSTER_QUERY_ROOT, principalId] },
      { throwOnError },
    ),
    queryClient.invalidateQueries({ queryKey: ['projects'] }, { throwOnError }),
  ]).then(() => undefined)
}

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
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
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
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
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
