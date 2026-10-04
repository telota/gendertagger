/** The server owns page order and the opaque continuation token. */
export const cursorQueryOptions = {
  initialPageParam: null as string | null,
  getNextPageParam: (page: { has_more: boolean; next_cursor?: string | null }) =>
    page.has_more ? (page.next_cursor ?? null) : undefined,
}

/** Callers supply the canonical server page, live-state predicate, interval, and error policy. */
export function liveListPolling<TPage extends { items: unknown[] }>(options: {
  isLive: (item: TPage['items'][number]) => boolean
  intervalMs: number
  stopOnError: boolean
}) {
  // An item-only page signature erases continuation fields during infinite-query inference.
  return (query: {
    state: { status: string; data: { pages: TPage[] } | undefined }
  }): number | false => {
    if (options.stopOnError && query.state.status === 'error') return false
    return query.state.data?.pages.some((page) => page.items.some(options.isLive))
      ? options.intervalMs
      : false
  }
}
