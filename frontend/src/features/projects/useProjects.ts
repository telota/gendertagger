import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import type { Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'

export type AccessibleProject = components['schemas']['AccessibleProject']

export interface ProjectCreateInput {
  displayName: string
  slug: string
  /** Empty means "no description", sent as `null` rather than an empty string. */
  description: string
}

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

/** `POST /projects` (D6: creation is a global-operator action, not a per-project one). */
export function useCreateProject() {
  const client = useApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: ProjectCreateInput) =>
      unwrap(
        client.POST('/api/v1/projects', {
          body: {
            display_name: input.displayName,
            slug: input.slug,
            description: input.description.trim() === '' ? null : input.description.trim(),
          },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY })
    },
  })
}
