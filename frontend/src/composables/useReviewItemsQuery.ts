import { useInfiniteQuery } from '@tanstack/vue-query'
import { ref, type Ref } from 'vue'

import { unwrap } from '@/api'
import { cursorQueryOptions } from '@/composables/cursorQuery'
import { reviewItemsResourceKey, type ReviewItemsQuery } from '@/composables/resourceQueries'
import { useApiClient } from '@/composables/useApiClient'
import { usePrivateQueryScope } from '@/composables/usePrivateQueryScope'

/** Native review-item reads; each screen supplies its own complete filter/sort tuple. */
export function useReviewItemsQuery(
  request: Readonly<Ref<Omit<ReviewItemsQuery, 'cursor'>>>,
  enabled: Ref<boolean> = ref(true),
) {
  const client = useApiClient()
  const scope = usePrivateQueryScope(enabled)
  const key = scope.key(() => reviewItemsResourceKey(request.value.aggregation_id, request.value))
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ queryKey, pageParam, signal }) =>
      unwrap(
        client.GET('/api/v1/review-items', {
          params: {
            query: {
              ...queryKey[3],
              ...(pageParam === null ? {} : { cursor: pageParam }),
            },
          },
          signal,
        }),
      ),
    ...cursorQueryOptions,
    enabled: scope.canRead,
  })
  return { ...query, data: scope.data(query, key) }
}
