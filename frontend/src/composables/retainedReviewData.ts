import type { QueryClient } from '@tanstack/vue-query'

import { ApiError } from '@/api'
import { currentData } from '@/composables/queryData'

/** Only transient transport/server failures may retain an already authorized review context. */
export function isRecoverableReviewError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    ((error.status === null && error.code === 'network_error') ||
      (error.status !== null && error.status >= 500))
  )
}

export function retainedReviewData<T>(
  cache: QueryClient,
  key: readonly unknown[],
  enabled: boolean,
  status: string,
  observed: T | undefined,
  error: unknown,
): T | undefined {
  if (status === 'error' && !isRecoverableReviewError(error)) return undefined
  return currentData(cache, key, enabled, status, observed)
}
