import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch, type Ref } from 'vue'

import { unwrap } from '@/api'
import type { components } from '@/api/schema'
import { useApiClient } from '@/composables/useApiClient'
import { usePolledQuery } from '@/composables/usePolledQuery'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'
import { useSessionStore } from '@/stores/session'

import {
  snapshotListKey,
  snapshotImportStatusKey,
  snapshotUploadLimitsKey,
} from '@/composables/resourceQueries'

type DatasetSnapshot = components['schemas']['DatasetSnapshot']
type SourceFormat = components['schemas']['SourceFormat']
type SourcePackaging = components['schemas']['SourcePackaging']

const TERMINAL_STATUSES = new Set<DatasetSnapshot['status']>(['ready', 'failed'])

export interface SnapshotImportInput {
  projectId: string
  sourceFormat: SourceFormat
  packaging: SourcePackaging
  /** Exactly one file unless `packaging` is `loose`, which repeats the `source` part per file. */
  files: readonly File[]
}

/**
 * `POST /projects/{project_id}/snapshots` for every `source_format` × `packaging` the backend
 * accepts (tabular formats only with `single`; the choice is the caller's).
 *
 * openapi-fetch's generated body type mirrors the multipart schema as a plain object; the actual
 * request needs a real `FormData` so the browser sets the multipart boundary itself. The cast is
 * exactly openapi-fetch's own documented pattern for a `multipart/form-data` request body.
 */
export function useImportSnapshot() {
  const client = useApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    onSuccess: (_snapshot, input) => {
      void queryClient.invalidateQueries({ queryKey: snapshotListKey(input.projectId) })
    },
    mutationFn: (input: SnapshotImportInput) => {
      const formData = new FormData()
      formData.append('packaging', input.packaging)
      formData.append('source_format', input.sourceFormat)
      for (const file of input.files) formData.append('source', file)
      return unwrap(
        client.POST('/api/v1/projects/{project_id}/snapshots', {
          params: { path: { project_id: input.projectId } },
          body: formData as unknown as components['schemas']['Body_import_snapshot_api_v1_projects__project_id__snapshots_post'],
        }),
      )
    },
  })
}

/** `GET /snapshots/{snapshot_id}`, polled until the import reaches `ready` or `failed`. */
export function useSnapshotStatus(
  snapshotId: Readonly<Ref<string | null>>,
  projectId?: Readonly<Ref<string>>,
) {
  const client = useApiClient()
  const session = useSessionStore()
  const queryClient = useQueryClient()

  const query = usePolledQuery({
    queryKey: computed(() =>
      snapshotImportStatusKey(session.user?.id, projectId?.value ?? null, snapshotId.value),
    ),
    queryFn: ({ signal }) => {
      const id = snapshotId.value
      if (id === null) throw new Error('useSnapshotStatus: no snapshot to poll yet.')
      return unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}', {
          params: { path: { snapshot_id: id } },
          signal,
        }),
      )
    },
    isTerminal: (snapshot) => TERMINAL_STATUSES.has(snapshot.status),
    enabled: computed(() => snapshotId.value !== null && session.canUsePrivateNavigation),
  })

  // The project's snapshot list is only ever invalidated once, at upload time, while this snapshot
  // is still pending — the list itself is never polled, so without this it would go on showing that
  // stale pending status (and e.g. hide a now-ready dataset from a generate step reading the list)
  // until something unrelated happened to refetch it.
  let invalidatedFor: string | null = null
  watch(query.data, (snapshot) => {
    const project = projectId?.value
    if (!snapshot || !project || !TERMINAL_STATUSES.has(snapshot.status)) return
    if (invalidatedFor === snapshot.id) return
    invalidatedFor = snapshot.id
    void queryClient.invalidateQueries({ queryKey: snapshotListKey(project) })
  })

  return query
}

/**
 * `GET /snapshot-upload-limits`: the deployment's bounds, readable before uploading so they can be
 * shown up front rather than only reported by a `413` afterwards.
 */
export function useSnapshotUploadLimits(enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(snapshotUploadLimitsKey)

  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => unwrap(client.GET('/api/v1/snapshot-upload-limits', { signal })),
    staleTime: Infinity,
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}
