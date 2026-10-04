import type { components } from '@/api/schema'

type ProjectRole = components['schemas']['ProjectRole']

const ROLE_LEVEL: Record<ProjectRole, number> = { viewer: 0, reviewer: 1, operator: 2 }

/** Present capabilities from the backend's effective project role, never from global grants. */
export function hasProjectRole(
  role: ProjectRole | null | undefined,
  minimum: ProjectRole,
): boolean {
  return role != null && ROLE_LEVEL[role] >= ROLE_LEVEL[minimum]
}
