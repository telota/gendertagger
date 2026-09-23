import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { usePolledQuery } from '@/composables/usePolledQuery'

import { snapshotListKey } from './useSnapshots'

export type DatasetSnapshot = components['schemas']['DatasetSnapshot']
export type SourceFormat = components['schemas']['SourceFormat']

const TERMINAL_STATUSES = new Set<DatasetSnapshot['status']>(['ready', 'failed'])

export interface SnapshotImportInput {
  projectId: string
  sourceFormat: SourceFormat
  file: File
}

/**
 * `POST /projects/{project_id}/snapshots`, single-file packaging only for now — the full
 * `source_format` × `packaging` matrix (folder, GitLab, loose/zip/tar.gz) is a later slice of M3.
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
      formData.append('packaging', 'single')
      formData.append('source_format', input.sourceFormat)
      formData.append('source', input.file)
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
export function useSnapshotStatus(snapshotId: Ref<string | null>) {
  const client = useApiClient()

  return usePolledQuery({
    queryKey: computed(() => ['snapshots', snapshotId.value] as const),
    queryFn: () => {
      const id = snapshotId.value
      if (id === null) throw new Error('useSnapshotStatus: no snapshot to poll yet.')
      return unwrap(
        client.GET('/api/v1/snapshots/{snapshot_id}', { params: { path: { snapshot_id: id } } }),
      )
    },
    isTerminal: (snapshot) => TERMINAL_STATUSES.has(snapshot.status),
    enabled: computed(() => snapshotId.value !== null),
  })
}
