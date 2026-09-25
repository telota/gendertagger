import { computed, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'

import { useAggregation } from '@/features/runs/useAggregations'
import { useRun } from '@/features/runs/useRunDetail'
import { useProject } from '@/features/projects/useProjects'
import { hasProjectRole, type ProjectRole } from '@/features/projects/projectRoles'
import { useSessionStore } from '@/stores/session'

export interface ProjectNavigationContext {
  projectId: string
  currentUserRole: ProjectRole
  /** The run the run-level entries lead to; `null` while the project has none to show. */
  runId: string | null
  aggregationId: string | null
  snapshotId: string | null
}

function stringParam(raw: string | string[] | undefined): string | null {
  const value = Array.isArray(raw) ? raw[0] : raw
  return value ? value : null
}

/**
 * What the sidebar's project group points at. The URL is the first authority: inside a run, an
 * aggregation or a snapshot the entries follow that very resource. Elsewhere in the project they
 * fall back to the project's working aggregation (ADR-0035), which the server set explicitly, and to
 * the run and snapshot that aggregation belongs to. A selected run or snapshot without an explicit
 * aggregation never borrows the working aggregation. Nothing is guessed from recency; an entry with
 * no target yet is reported as `null` so the sidebar can show it disabled instead of a dead link.
 */
export function useProjectNavigation(): ComputedRef<ProjectNavigationContext | null> {
  const route = useRoute()
  const session = useSessionStore()

  const projectId = computed(() => stringParam(route.params.projectId) ?? '')
  const routeRunId = computed(() => stringParam(route.params.runId))
  const routeAggregationId = computed(() => stringParam(route.params.aggregationId))
  const routeSnapshotId = computed(() => stringParam(route.params.snapshotId))
  const projectQuery = useProject(
    projectId,
    computed(() => session.canUsePrivateNavigation && projectId.value !== ''),
  )
  const currentProject = computed(() => {
    if (!session.canUsePrivateNavigation || !projectQuery.isSuccess.value) return null
    const project = projectQuery.data.value
    return project?.id === projectId.value && hasProjectRole(project.current_user_role, 'viewer')
      ? project
      : null
  })

  const aggregationId = computed(() => {
    if (routeAggregationId.value !== null) return routeAggregationId.value
    if (routeRunId.value !== null || routeSnapshotId.value !== null) return null
    return currentProject.value?.working_aggregation_execution_id ?? null
  })
  const aggregationQuery = useAggregation(
    computed(() => aggregationId.value ?? ''),
    computed(
      () =>
        currentProject.value !== null && routeRunId.value === null && aggregationId.value !== null,
    ),
  )

  const runId = computed(
    () =>
      routeRunId.value ??
      (aggregationId.value === null ? null : (aggregationQuery.data.value?.run_id ?? null)),
  )
  const runQuery = useRun(
    computed(() => runId.value ?? ''),
    computed(
      () => currentProject.value !== null && routeSnapshotId.value === null && runId.value !== null,
    ),
  )

  return computed(() => {
    const project = currentProject.value
    if (project === null) {
      return null
    }
    return {
      projectId: projectId.value,
      currentUserRole: project.current_user_role,
      runId: runId.value,
      aggregationId: aggregationId.value,
      snapshotId:
        routeSnapshotId.value ??
        (runId.value === null ? null : (runQuery.data.value?.dataset_snapshot_id ?? null)),
    }
  })
}
