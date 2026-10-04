import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, type Ref } from 'vue'
import { ApiError, unwrap } from '@/api'
import type { components } from '@/api/schema'
import { useApiClient } from '@/composables/useApiClient'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import {
  PROJECTS_QUERY_KEY,
  projectEligibleUsersKey,
  projectMembershipQueryKey,
} from '@/composables/resourceQueries'

export type ProjectMembershipError =
  | 'project_manager_conflict'
  | 'team_membership_conflict'
  | 'resource_not_found'
  | 'forbidden'
  | 'validation_error'
  | 'authentication_required'
  | 'network_error'
  | 'unexpected'
function code(error: unknown): ProjectMembershipError {
  if (!(error instanceof ApiError)) return 'unexpected'
  switch (error.code) {
    case 'project_manager_conflict':
    case 'team_membership_conflict':
    case 'resource_not_found':
    case 'forbidden':
    case 'validation_error':
    case 'authentication_required':
    case 'network_error':
      return error.code
    default:
      return 'unexpected'
  }
}

/** Shared authorized membership state; it exposes no scientific project data. */
export function useProjectMembershipState(
  projectId: Readonly<Ref<string>>,
  principalId: Readonly<Ref<string | null>>,
  enabled: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  return useQuery({
    queryKey: computed(() => projectMembershipQueryKey(principalId.value, projectId.value)),
    queryFn: ({ signal, queryKey }) =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}/members', {
          params: { path: { project_id: queryKey[2] } },
          signal,
        }),
      ),
    enabled,
  })
}

export function useProjectMembership(
  projectId: Readonly<Ref<string>>,
  principalId: Readonly<Ref<string | null>>,
  enabled: Readonly<Ref<boolean>>,
) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const error = ref<ProjectMembershipError | null>(null)
  const pending = ref(false)
  let epoch = 0
  const state = useProjectMembershipState(projectId, principalId, enabled)
  const candidates = useInfiniteQuery({
    queryKey: computed(() => projectEligibleUsersKey(principalId.value, projectId.value)),
    queryFn: ({ pageParam, signal, queryKey }) =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}/eligible-users', {
          params: {
            path: { project_id: queryKey[2] },
            query: { query: null, cursor: pageParam },
          },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled,
  })
  async function mutate<T>(request: () => Promise<T>): Promise<T | null> {
    const principal = principalId.value
    const current = epoch
    if (principal === null || pending.value) return null
    pending.value = true
    error.value = null
    try {
      const value = await request()
      if (epoch !== current || principalId.value !== principal) return null
      void Promise.all([
        queryClient.invalidateQueries({
          queryKey: projectMembershipQueryKey(principal, projectId.value),
        }),
        queryClient.invalidateQueries({
          queryKey: projectEligibleUsersKey(principal, projectId.value),
        }),
        queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY }),
      ])
      return value
    } catch (e) {
      if (epoch === current) error.value = code(e)
      return null
    } finally {
      if (epoch === current) pending.value = false
    }
  }
  const setRole = (userId: string, role: components['schemas']['ProjectRole']) =>
    mutate(() =>
      unwrap(
        client.PUT('/api/v1/projects/{project_id}/members/{user_id}', {
          params: { path: { project_id: projectId.value, user_id: userId } },
          body: { role },
        }),
      ),
    )
  const removeRole = (userId: string) =>
    mutate(() =>
      unwrap(
        client.DELETE('/api/v1/projects/{project_id}/members/{user_id}', {
          params: { path: { project_id: projectId.value, user_id: userId } },
        }),
      ),
    )
  const transfer = (managerUserId: string, expectedManagerUserId: string) =>
    mutate(() =>
      unwrap(
        client.PUT('/api/v1/projects/{project_id}/manager', {
          params: { path: { project_id: projectId.value } },
          body: { manager_user_id: managerUserId, expected_manager_user_id: expectedManagerUserId },
        }),
      ),
    )
  return {
    state,
    candidates,
    error,
    pending,
    setRole,
    removeRole,
    transfer,
    clear: () => {
      epoch += 1
      error.value = null
      pending.value = false
    },
  }
}
