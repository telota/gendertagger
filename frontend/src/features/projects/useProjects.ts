import { useInfiniteQuery, useQuery } from '@tanstack/vue-query'
import { computed, ref, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useSessionStore } from '@/stores/session'

export type AccessibleProject = components['schemas']['AccessibleProject']

/**
 * `GET /projects`, cursor-paginated (docs/23-wireframe-ui-inventory.md: server state through
 * TanStack Query, never re-sorted or re-filtered in the browser). `enabled` lets a caller hold the
 * request until it knows the visitor is signed in, rather than firing a request bound to fail.
 */
export function useProjectList(enabled: Ref<boolean>) {
  const client = useApiClient()
  const session = useSessionStore()

  return useInfiniteQuery({
    queryKey: computed(() => ['projects', 'list', session.user?.id ?? 'anonymous'] as const),
    queryFn: ({ pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/projects', {
          params: { query: { cursor: pageParam ?? null } },
          signal,
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? null) : undefined,
    enabled: computed(() => enabled.value && session.canUsePrivateNavigation),
  })
}

/**
 * `GET /projects/{project_id}` — one project, for its own detail screen. A screen passes its
 * signed-in state as `enabled`, so a visitor without a session (about to be sent to /login) causes
 * no request at all.
 */
export function useProject(projectId: Ref<string>, enabled: Ref<boolean> = ref(true)) {
  const client = useApiClient()
  const session = useSessionStore()

  return useQuery({
    // AccessibleProject includes caller-specific roles and must never be shared across accounts.
    queryKey: computed(
      () => ['projects', projectId.value, session.user?.id ?? 'anonymous'] as const,
    ),
    queryFn: ({ queryKey, signal }) =>
      unwrap(
        client.GET('/api/v1/projects/{project_id}', {
          params: { path: { project_id: queryKey[1] } },
          signal,
        }),
      ),
    enabled: computed(() => enabled.value && session.canUsePrivateNavigation),
  })
}
