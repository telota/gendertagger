import type { QueryClient } from '@tanstack/vue-query'

import { ApiError } from '@/api'

/** Resolve the exact current cache key before rendering; an observer can lag a route/account change. */
export function currentData<T>(
  client: QueryClient,
  key: readonly unknown[],
  enabled: boolean,
  status: string,
  observed: T | undefined,
): T | undefined {
  if (!enabled || status === 'pending' || observed === undefined) return undefined
  const state = client.getQueryState<T>(key)
  const error = state?.error
  if (error instanceof ApiError && error.status !== null && [401, 403, 404].includes(error.status))
    return undefined
  return state?.data
}
