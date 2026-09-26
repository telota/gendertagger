import { useQueryClient } from '@tanstack/vue-query'
import { computed, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'

import { useAggregation } from '@/features/runs/useAggregations'
import { useRun } from '@/features/runs/useRunDetail'
import type { ProjectRole } from '@/features/projects/projectRoles'
import { useImportedSnapshot } from '@/features/projects/useSnapshotData'
import { useProjectIdentity } from './useProjectIdentity'

export interface ProjectNavigationContext {
  projectId: string
  /** Null identifies a management-only context, without scientific project access. */
  currentUserRole: ProjectRole | null
  currentUserCanManageMembers: boolean
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
 * Resolve only explicitly selected URL resources. Project task entry is independent of this
 * context; the working aggregation is a picker recommendation, never an implicit selection.
 * Resource relationships must resolve back to this project before becoming navigation targets.
 */
export function useProjectNavigation(): ComputedRef<ProjectNavigationContext | null> {
  const route = useRoute()
  const cache = useQueryClient()
  const { projectId, project: currentProject, canManageMembers } = useProjectIdentity()
  const routeRunId = computed(() => stringParam(route.params.runId))
  const routeAggregationId = computed(() => stringParam(route.params.aggregationId))
  const routeSnapshotId = computed(() => stringParam(route.params.snapshotId))
  const aggregationId = routeAggregationId
  const aggregationQuery = useAggregation(
    computed(() => aggregationId.value ?? ''),
    computed(() => currentProject.value !== null && aggregationId.value !== null),
  )
  const aggregation = computed(() => {
    if (!aggregationQuery.isSuccess.value || !aggregationQuery.data.value) return null
    const key = ['aggregations', aggregationId.value] as const
    if (cache.getQueryState(key)?.status !== 'success') return null
    const value = cache.getQueryData<typeof aggregationQuery.data.value>(key)
    return value?.id === aggregationId.value ? value : null
  })

  const runId = computed(
    () =>
      routeRunId.value ??
      (aggregationId.value === null ? null : (aggregation.value?.run_id ?? null)),
  )
  const runQuery = useRun(
    computed(() => runId.value ?? ''),
    computed(() => currentProject.value !== null && runId.value !== null),
  )
  const run = computed(() => {
    if (!runQuery.isSuccess.value || !runQuery.data.value) return null
    const key = ['runs', runId.value] as const
    if (cache.getQueryState(key)?.status !== 'success') return null
    const value = cache.getQueryData<typeof runQuery.data.value>(key)
    return value?.id === runId.value ? value : null
  })
  const snapshotId = computed(
    () =>
      routeSnapshotId.value ??
      (runId.value === null ? null : (run.value?.dataset_snapshot_id ?? null)),
  )
  const snapshotQuery = useImportedSnapshot(
    projectId,
    computed(() => snapshotId.value ?? ''),
    computed(() => currentProject.value !== null && snapshotId.value !== null),
  )

  return computed(() => {
    const project = currentProject.value
    if (project === null) {
      return canManageMembers.value
        ? {
            projectId: projectId.value,
            currentUserRole: null,
            currentUserCanManageMembers: true,
            runId: null,
            aggregationId: null,
            snapshotId: null,
          }
        : null
    }
    const snapshot = snapshotQuery.isSuccess.value ? snapshotQuery.data.value : undefined
    const validSnapshotId =
      snapshot?.id === snapshotId.value && snapshot.project_id === projectId.value
        ? snapshot.id
        : null
    const validRunId =
      validSnapshotId !== null && run.value?.dataset_snapshot_id === validSnapshotId
        ? run.value.id
        : null
    return {
      projectId: projectId.value,
      currentUserRole: project.current_user_role,
      currentUserCanManageMembers: canManageMembers.value,
      runId: validRunId,
      aggregationId:
        validRunId !== null &&
        aggregation.value?.run_id === validRunId &&
        aggregation.value.status === 'completed'
          ? aggregation.value.id
          : null,
      snapshotId: validSnapshotId,
    }
  })
}
