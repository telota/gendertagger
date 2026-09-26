import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, type Ref } from 'vue'

import { unwrap, type components } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { useSessionStore } from '@/stores/session'

export type AccessibleProject = components['schemas']['AccessibleProject']

/**
 * `GET /projects`, cursor-paginated (docs/23-wireframe-ui-inventory.md: server state through
 * TanStack Query, never re-sorted or re-filtered in the browser). `enabled` lets a caller hold the
 * request until it knows the visitor is signed in, rather than firing a request bound to fail.
 *
 * A bounded `pageSize` gets its own cache entry so dashboard previews never truncate the complete
 * project list or project switcher.
 */
export function useProjectList(enabled: Ref<boolean>, pageSize?: number) {
  const client = useApiClient()
  const session = useSessionStore()

  return useInfiniteQuery({
    queryKey: computed(() =>
      pageSize === undefined
        ? (['projects', 'list', session.user?.id ?? 'anonymous'] as const)
        : (['projects', 'list', 'preview', pageSize, session.user?.id ?? 'anonymous'] as const),
    ),
    queryFn: ({ pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/projects', {
          params: {
            query: {
              cursor: pageParam ?? null,
              ...(pageSize === undefined ? {} : { limit: pageSize }),
            },
          },
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

/** Project-operator switch for the optional game path. The server remains authoritative. */
export function useSetProjectGameMode(projectId: Ref<string>) {
  const client = useApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (enabled: boolean) =>
      unwrap(
        client.PUT('/api/v1/projects/{project_id}/game-mode', {
          params: { path: { project_id: projectId.value } },
          body: { enabled },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['projects'] }),
  })
}
