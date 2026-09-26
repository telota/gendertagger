import { useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError } from '@/api'
import { hasProjectRole } from '@/features/projects/projectRoles'
import {
  projectMembershipQueryKey,
  useProjectMembershipState,
  type ProjectMembershipState,
} from '@/features/projects/useProjectMembership'
import { useProject, type AccessibleProject } from '@/features/projects/useProjects'
import { useSessionStore } from '@/stores/session'

/** Authorized project identity for shell presentation; resource context stays with the view. */
export function useProjectIdentity() {
  const route = useRoute()
  const session = useSessionStore()
  const queryClient = useQueryClient()
  const principalId = computed(() => session.user?.id ?? null)
  const projectId = computed(() => {
    const raw = route.params.projectId
    return (Array.isArray(raw) ? raw[0] : raw) ?? ''
  })
  const isProjectRoute = computed(() => projectId.value !== '')
  const isMembershipRoute = computed(() => route.name === 'projectMembers')
  const membershipQuery = useProjectMembershipState(
    projectId,
    principalId,
    computed(() => isMembershipRoute.value && session.canUsePrivateNavigation),
  )
  const membership = computed(() => {
    if (
      !session.canUsePrivateNavigation ||
      !isMembershipRoute.value ||
      !membershipQuery.isSuccess.value ||
      !membershipQuery.data.value
    )
      return null
    const key = projectMembershipQueryKey(principalId.value, projectId.value)
    if (queryClient.getQueryState(key)?.status !== 'success') return null
    return queryClient.getQueryData<ProjectMembershipState>(key) ?? null
  })
  const canManageMembership = computed(() => {
    const value = membership.value
    return (
      value !== null &&
      (session.user?.roles.includes('admin') === true ||
        value.manager.user_id === principalId.value)
    )
  })
  function hasOwnReadRole(value: ProjectMembershipState): boolean {
    if (session.user?.roles.includes('admin')) return true
    const ownRole =
      value.manager.user_id === principalId.value
        ? value.manager.project_role
        : value.members.find(
            (member) =>
              member.user_id === principalId.value && member.project_id === projectId.value,
          )?.role
    return ownRole !== null && ownRole !== undefined && hasProjectRole(ownRole, 'viewer')
  }
  const resolvedProjectReadAt = ref<number | null>(null)
  const canReadMembershipProject = computed(() => {
    const value = membership.value
    if (value !== null) return hasOwnReadRole(value)
    const membershipKey = projectMembershipQueryKey(principalId.value, projectId.value)
    const state = queryClient.getQueryState(membershipKey)
    const error = state?.error
    if (
      !membershipQuery.isError.value ||
      state?.status !== 'error' ||
      !(error instanceof ApiError) ||
      (error.status !== 403 && error.status !== 404) ||
      resolvedProjectReadAt.value === null
    )
      return false
    // Transfer can revoke roster access while preserving the caller's ordinary project role.
    // A prior successful roster explicitly denying that role remains revocation evidence even
    // after a later roster error, unless an independently authorized project read is newer.
    const retained = queryClient.getQueryData<ProjectMembershipState>(membershipKey)
    return (
      retained === undefined ||
      hasOwnReadRole(retained) ||
      resolvedProjectReadAt.value > state.dataUpdatedAt
    )
  })
  // A management URL alone never authorizes fetching research data (ADR-0042). Resolve the
  // existing membership state first; only the caller's own ordinary role or admin access enables it.
  const canReadProject = computed(
    () =>
      isProjectRoute.value &&
      session.canUsePrivateNavigation &&
      (!isMembershipRoute.value || canReadMembershipProject.value),
  )
  const query = useProject(projectId, canReadProject)
  watch(
    [principalId, projectId, query.isSuccess, query.data, query.dataUpdatedAt],
    () => {
      const key = ['projects', projectId.value, principalId.value ?? 'anonymous'] as const
      const value = queryClient.getQueryData<AccessibleProject>(key)
      const state = queryClient.getQueryState(key)
      resolvedProjectReadAt.value =
        state?.status === 'success' &&
        value?.id === projectId.value &&
        hasProjectRole(value.current_user_role, 'viewer')
          ? state.dataUpdatedAt
          : null
    },
    { immediate: true, flush: 'sync' },
  )
  const project = computed(() => {
    if (!canReadProject.value || !query.isSuccess.value || !query.data.value) return null
    const key = ['projects', projectId.value, principalId.value ?? 'anonymous'] as const
    if (queryClient.getQueryState(key)?.status !== 'success') return null
    const value = queryClient.getQueryData<AccessibleProject>(key)
    return value?.id === projectId.value && hasProjectRole(value.current_user_role, 'viewer')
      ? value
      : null
  })
  const canManageMembers = computed(() =>
    isMembershipRoute.value
      ? canManageMembership.value
      : project.value?.current_user_can_manage_members === true,
  )

  return { projectId, project, query, isProjectRoute, canManageMembers }
}
