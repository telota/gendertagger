import { useInfiniteQuery, useQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

export type AccessibleProject = components['schemas']['AccessibleProject']

/** One query key for the whole list — server-side sort is fixed (slug order), so there is no filter tuple yet. */
const PROJECTS_QUERY_KEY = ['projects'] as const

/**
 * `GET /projects`, cursor-paginated (docs/23-wireframe-ui-inventory.md: server state through
 * TanStack Query, never re-sorted or re-filtered in the browser). `enabled` lets a caller hold the
 * request until it knows the visitor is signed in, rather than firing a request bound to fail.
 */
export function useProjectList(enabled: Ref<boolean>) {
  const client = useApiClient()

  return useInfiniteQuery({
    queryKey: PROJECTS_QUERY_KEY,
    queryFn: ({ pageParam }) =>
      unwrap(client.GET('/api/v1/projects', { params: { query: { cursor: pageParam ?? null } } })),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
    enabled,
  })
}

/** `GET /projects/{project_id}` — one project, for its own detail screen. */
export function useProject(projectId: Ref<string>) {
  const client = useApiClient()

  return useQuery({
    queryKey: computed(() => ['projects', projectId.value] as const),
    queryFn: () =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}', {
          params: { path: { project_id: projectId.value } },
        }),
      ),
  })
}
