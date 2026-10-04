import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { privateQueryKey } from '@/composables/usePrivateQueryScope'
import { useBulkDecision } from '@/features/review/useBulkDecision'
import type { ReviewItem } from '@/features/review/useReviewData'
import { useSessionStore } from '@/stores/session'

import { waitFor } from '../../helpers/wait'
import { item, newServer, reviewClient, SNAPSHOT_ID, type Server } from './fixtures'

const USER = { id: 'account-a', display_name: 'Reviewer A', roles: [] }
const OTHER_USER = { id: 'account-b', display_name: 'Reviewer B', roles: [] }
const mounted: VueWrapper[] = []
const caches: QueryClient[] = []
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  for (const cache of caches.splice(0)) cache.clear()
  vi.restoreAllMocks()
})

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((finish) => {
    resolve = finish
  })
  return { promise, resolve }
}

function mountBulkDecision(server: Server) {
  const cache = new QueryClient()
  caches.push(cache)
  let session!: ReturnType<typeof useSessionStore>
  let bulk!: ReturnType<typeof useBulkDecision>
  const wrapper = mount(
    defineComponent({
      setup() {
        session = useSessionStore()
        session.user = USER
        session.status = 'ready'
        bulk = useBulkDecision()
        return () => null
      },
    }),
    {
      global: {
        plugins: [createPinia(), [VueQueryPlugin, { queryClient: cache }]],
        provide: { [API_CLIENT_KEY as symbol]: reviewClient(server) },
      },
    },
  )
  mounted.push(wrapper)
  return { bulk, cache, session }
}

const PEOPLE = [item('demo-1'), item('demo-2')] as ReviewItem[]
const SPEC = { action: 'defer', label: null, comment: 'Check sources' } as const

describe('bulk decision ownership', () => {
  describe.each(['ok', 'forbidden'] as const)('late first response: %s', (postOutcome) => {
    it.each([
      { name: 'account replacement', principals: [OTHER_USER] },
      { name: 'A to B to A replacement', principals: [OTHER_USER, USER] },
      { name: 'logout then same-account sign-in', principals: [null, USER] },
    ])('stops $name before publishing or dispatching another person', async ({ principals }) => {
      const firstResponse = deferred()
      const server = newServer({ gate: firstResponse.promise, postOutcome })
      const { bulk, cache, session } = mountBulkDecision(server)
      const invalidate = vi.spyOn(cache, 'invalidateQueries')
      const pending = bulk.run(PEOPLE, SPEC)
      await waitFor(() => expect(server.posts).toHaveLength(1))

      for (const principal of principals) session.user = principal
      expect(bulk.phase.value).toBe('idle')
      expect(bulk.total.value).toBe(0)
      expect(bulk.results.value).toEqual([])
      firstResponse.resolve()

      await expect(pending).resolves.toEqual([])
      expect(server.posts).toHaveLength(1)
      expect(bulk.phase.value).toBe('idle')
      expect(bulk.results.value).toEqual([])
      expect(invalidate).not.toHaveBeenCalled()
    })
  })

  it('removes already published outcomes synchronously and ignores the remaining old response', async () => {
    const firstResponse = deferred()
    const secondResponse = deferred()
    const server = newServer({ gate: firstResponse.promise })
    const { bulk, cache, session } = mountBulkDecision(server)
    const invalidate = vi.spyOn(cache, 'invalidateQueries')
    const pending = bulk.run(PEOPLE, SPEC)
    await waitFor(() => expect(server.posts).toHaveLength(1))
    server.gate = secondResponse.promise
    firstResponse.resolve()
    await waitFor(() => expect(server.posts).toHaveLength(2))
    expect(bulk.results.value).toHaveLength(1)

    session.user = OTHER_USER
    expect(bulk.results.value).toEqual([])
    expect(bulk.phase.value).toBe('idle')
    secondResponse.resolve()

    await expect(pending).resolves.toEqual([])
    expect(bulk.results.value).toEqual([])
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('preserves same-account recovery and refreshes the original principal projections', async () => {
    const firstResponse = deferred()
    const server = newServer({ gate: firstResponse.promise })
    const { bulk, cache, session } = mountBulkDecision(server)
    const ownKey = privateQueryKey(['aggregations', 'aggregation-1', 'review-summary'], USER.id)
    const otherKey = privateQueryKey(
      ['aggregations', 'aggregation-1', 'review-summary'],
      OTHER_USER.id,
    )
    cache.setQueryData(ownKey, {})
    cache.setQueryData(otherKey, {})
    const pending = bulk.run(PEOPLE, SPEC)
    await waitFor(() => expect(server.posts).toHaveLength(1))

    session.isAuthenticating = true
    session.user = { ...USER }
    session.isAuthenticating = false
    expect(bulk.phase.value).toBe('running')
    firstResponse.resolve()

    await expect(pending).resolves.toEqual([
      { teiId: 'demo-1', outcome: { kind: 'saved', revision: 3 } },
      { teiId: 'demo-2', outcome: { kind: 'saved', revision: 4 } },
    ])
    expect(server.posts.map((post) => post.tei_id)).toEqual(['demo-1', 'demo-2'])
    expect(bulk.phase.value).toBe('done')
    expect(cache.getQueryState(ownKey)?.isInvalidated).toBe(true)
    expect(cache.getQueryState(otherKey)?.isInvalidated).toBe(false)
    expect(server.posts.every((post) => post.snapshot_id === SNAPSHOT_ID)).toBe(true)
  })
})
