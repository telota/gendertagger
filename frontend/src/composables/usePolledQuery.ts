import { useQuery, type UseQueryReturnType } from '@tanstack/vue-query'
import type { MaybeRefOrGetter } from 'vue'

// A short, human-scale refresh; nothing scientific rides on this exact number.
const POLL_INTERVAL_MS = 2000

/**
 * The `202` → poll → terminal-state pattern shared by snapshots, aggregations, evaluations, and
 * exports (docs/23-wireframe-ui-inventory.md's "async resource polling" cross-cutting concern) —
 * built generically the first time it's needed, since the document already names four consumers.
 *
 * `isTerminal` decides when to stop; until the first response arrives there is nothing to test yet,
 * so polling continues. `queryKey` and `enabled` accept a ref or getter and stay reactive, exactly
 * as `useQuery`'s own do.
 */
export function usePolledQuery<T>(options: {
  queryKey: MaybeRefOrGetter<readonly unknown[]>
  queryFn: () => Promise<T>
  isTerminal: (data: T) => boolean
  enabled?: MaybeRefOrGetter<boolean>
}): UseQueryReturnType<T, Error> {
  return useQuery<T, Error, T, readonly unknown[]>({
    queryKey: options.queryKey,
    queryFn: options.queryFn,
    enabled: options.enabled,
    refetchInterval: (query) => {
      const data = query.state.data
      return data === undefined || !options.isTerminal(data) ? POLL_INTERVAL_MS : false
    },
  })
}
