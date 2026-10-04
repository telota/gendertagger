import { useInfiniteQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'
import { unwrap } from '@/api'
import { useApiClient } from '@/composables/useApiClient'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import { managedProjectsKey } from '@/composables/resourceQueries'
export function useManagedProjects(
  enabled: Readonly<Ref<boolean>>,
  principalId: Readonly<Ref<string | null>>,
) {
  const client = useApiClient()
  return useInfiniteQuery({
    queryKey: computed(() => managedProjectsKey(principalId.value)),
    queryFn: ({ pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/projects/managed', {
          params: { query: { cursor: pageParam }, signal },
        }),
      ),
    ...cursorQueryOptions,
    enabled,
  })
}
