import { useInfiniteQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'
import { unwrap } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
export function useManagedProjects(
  enabled: Readonly<Ref<boolean>>,
  principalId: Readonly<Ref<string | null>>,
) {
  const client = useApiClient()
  return useInfiniteQuery({
    queryKey: computed(() => ['managed-projects', principalId.value ?? 'anonymous'] as const),
    queryFn: ({ pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/projects/managed', {
          params: { query: { cursor: pageParam }, signal },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => (page.has_more ? (page.next_cursor ?? null) : undefined),
    enabled,
  })
}
