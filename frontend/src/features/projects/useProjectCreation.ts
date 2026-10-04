import { useInfiniteQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'

import { ApiError, unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useDebouncedValue } from '@/composables/useDebouncedValue'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import {
  PROJECTS_QUERY_KEY,
  projectCreationTeamsKey,
  projectCreationRosterKey,
} from '@/composables/resourceQueries'

export type ProjectCreationError =
  | 'forbidden'
  | 'resource_not_found'
  | 'validation_error'
  | 'authentication_required'
  | 'password_change_required'
  | 'network_error'
  | 'unexpected'

const SEARCH_DEBOUNCE_MS = 300

function errorCode(error: unknown): ProjectCreationError {
  if (!(error instanceof ApiError)) return 'unexpected'
  switch (error.code) {
    case 'forbidden':
    case 'resource_not_found':
    case 'validation_error':
    case 'authentication_required':
    case 'password_change_required':
    case 'network_error':
      return error.code
    default:
      return 'unexpected'
  }
}

/** Team-aware project creation without inferring administrator team eligibility from discovery. */
export function useProjectCreation(
  principalId: Readonly<Ref<string | null>>,
  canCreate: Readonly<Ref<boolean>>,
  isAdministrator: Readonly<Ref<boolean>>,
  teamSearchInput: Ref<string>,
  selectedTeamId: Ref<string | null>,
) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const teamSearch = useDebouncedValue(teamSearchInput, SEARCH_DEBOUNCE_MS)
  const enabled = computed(() => canCreate.value && principalId.value !== null)
  const managerEnabled = computed(
    () => enabled.value && isAdministrator.value && selectedTeamId.value !== null,
  )
  const isSubmitting = ref(false)
  const error = ref<ProjectCreationError | null>(null)
  const refreshFailed = ref(false)
  let epoch = 0

  const teamsQuery = useInfiniteQuery({
    queryKey: computed(() => projectCreationTeamsKey(principalId.value, teamSearch.value.trim())),
    queryFn: ({ pageParam, signal, queryKey }) =>
      unwrap(
        client.GET('/api/v1/teams', {
          params: { query: { query: queryKey[3] || null, cursor: pageParam } },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled,
  })

  const managerQuery = useInfiniteQuery({
    queryKey: computed(() => projectCreationRosterKey(principalId.value, selectedTeamId.value)),
    queryFn: ({ pageParam, signal, queryKey }) =>
      unwrap(
        client.GET('/api/v1/admin/teams/{team_id}/members', {
          params: {
            path: { team_id: queryKey[3] },
            query: { query: null, cursor: pageParam },
          },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled: managerEnabled,
  })

  async function create(command: components['schemas']['ProjectCreate']) {
    const principal = principalId.value
    const requestEpoch = epoch
    if (principal === null || !enabled.value || isSubmitting.value) return null
    isSubmitting.value = true
    error.value = null
    refreshFailed.value = false
    try {
      const project = await unwrap(client.POST('/api/v1/projects', { body: command }))
      if (epoch !== requestEpoch || principalId.value !== principal) return null
      void queryClient
        .invalidateQueries({ queryKey: PROJECTS_QUERY_KEY }, { throwOnError: true })
        .catch(() => {
          if (epoch === requestEpoch && principalId.value === principal) refreshFailed.value = true
        })
      return project
    } catch (requestError) {
      if (epoch === requestEpoch && principalId.value === principal)
        error.value = errorCode(requestError)
      return null
    } finally {
      if (epoch === requestEpoch && principalId.value === principal) isSubmitting.value = false
    }
  }

  function clear(): void {
    epoch += 1
    isSubmitting.value = false
    error.value = null
    refreshFailed.value = false
  }

  watch(teamSearch, (_, previous) => {
    const principal = principalId.value
    if (principal !== null)
      void queryClient.cancelQueries({
        queryKey: projectCreationTeamsKey(principal, previous.trim()),
      })
  })
  watch([principalId, canCreate, selectedTeamId], clear)
  onScopeDispose(clear)

  return { teamsQuery, managerQuery, teamSearch, isSubmitting, error, refreshFailed, create, clear }
}
