import { computed, type Ref } from 'vue'

import { useProjectIdentity } from '@/app/useProjectIdentity'
import { useRouteParam } from '@/composables/useRequireSession'
import { useImportedSnapshot } from '@/features/projects/useSnapshotData'
import { useSessionStore } from '@/stores/session'

import { useRun } from './useRunDetail'

interface ArtifactQuery<T> {
  data: Ref<T | undefined>
  isError: Ref<boolean>
  isFetching: Ref<boolean>
  refetch: () => Promise<unknown>
}

/** Resolve canonical ownership before exposing an artifact beneath the current project/run URL. */
export function useArtifactRouteContext<T extends { id: string; run_id: string }>(
  resourceId: Ref<string>,
  resource: ArtifactQuery<T>,
) {
  const session = useSessionStore()
  const canRead = computed(() => session.canUsePrivateNavigation)
  const { projectId, project, query: projectQuery } = useProjectIdentity()
  const runId = useRouteParam('runId')
  const matchesResource = computed(
    () =>
      resource.data.value?.id === resourceId.value && resource.data.value.run_id === runId.value,
  )
  const canReadRun = computed(() => project.value !== null && matchesResource.value)
  const runQuery = useRun(runId, canReadRun)
  const matchesRun = computed(() => runQuery.data.value?.id === runId.value)
  const snapshotId = computed(() =>
    canReadRun.value && matchesRun.value ? (runQuery.data.value?.dataset_snapshot_id ?? '') : '',
  )
  const canReadSnapshot = computed(() => canReadRun.value && snapshotId.value !== '')
  const snapshot = useImportedSnapshot(projectId, snapshotId, canReadSnapshot)
  const matchesSnapshot = computed(
    () =>
      snapshot.data.value?.id === snapshotId.value &&
      snapshot.data.value.project_id === projectId.value,
  )
  const isError = computed(
    () =>
      canRead.value &&
      (resource.isError.value ||
        projectQuery.isError.value ||
        (projectQuery.isSuccess.value &&
          projectQuery.data.value !== undefined &&
          project.value === null) ||
        (resource.data.value !== undefined && !matchesResource.value) ||
        (canReadRun.value && runQuery.isError.value) ||
        (runQuery.data.value !== undefined && !matchesRun.value) ||
        (canReadSnapshot.value && snapshot.isError.value) ||
        (snapshot.data.value !== undefined && !matchesSnapshot.value)),
  )
  const valid = computed(
    () =>
      canRead.value &&
      !isError.value &&
      canReadRun.value &&
      matchesRun.value &&
      matchesSnapshot.value,
  )
  const data = computed(() => (valid.value ? resource.data.value : undefined))
  const run = computed(() => (valid.value ? runQuery.data.value : undefined))
  const isPending = computed(() => !isError.value && !valid.value)
  const isFetching = computed(
    () =>
      resource.isFetching.value ||
      projectQuery.isFetching.value ||
      (canReadRun.value && runQuery.isFetching.value) ||
      (canReadSnapshot.value && snapshot.isFetching.value),
  )

  async function refetch(): Promise<void> {
    await Promise.all([
      resource.refetch(),
      projectQuery.refetch(),
      ...(canReadRun.value ? [runQuery.refetch()] : []),
      ...(canReadSnapshot.value ? [snapshot.refetch()] : []),
    ])
  }

  return { data, run, snapshotId, valid, isPending, isError, isFetching, refetch }
}
