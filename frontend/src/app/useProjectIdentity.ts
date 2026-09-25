import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { hasProjectRole } from '@/features/projects/projectRoles'
import { useProject } from '@/features/projects/useProjects'
import { useSessionStore } from '@/stores/session'

/** Authorized project identity for shell presentation; resource context stays with the view. */
export function useProjectIdentity() {
  const route = useRoute()
  const session = useSessionStore()
  const projectId = computed(() => {
    const raw = route.params.projectId
    return (Array.isArray(raw) ? raw[0] : raw) ?? ''
  })
  const isProjectRoute = computed(() => projectId.value !== '')
  const query = useProject(
    projectId,
    computed(() => isProjectRoute.value && session.canUsePrivateNavigation),
  )
  const project = computed(() => {
    if (!session.canUsePrivateNavigation || !isProjectRoute.value || !query.isSuccess.value)
      return null
    const value = query.data.value
    return value?.id === projectId.value && hasProjectRole(value.current_user_role, 'viewer')
      ? value
      : null
  })

  return { projectId, project, query, isProjectRoute }
}
