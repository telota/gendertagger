import { QueryClient } from '@tanstack/vue-query'

/**
 * The shared server-state cache (docs/23-wireframe-ui-inventory.md: "a query/cache library" for
 * cursor-paginated collections and long-running polls). Retries are off: every failure this app
 * needs to recover from already has its own designed path (the `401` retry in `api/client.ts`, a
 * `202`-poll composable still to come) rather than TanStack Query's generic retry-with-backoff,
 * which would otherwise delay an error state behind silent, undesigned attempts.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}
