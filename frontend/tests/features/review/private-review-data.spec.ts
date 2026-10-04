import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { computed, defineComponent, h, ref, type Ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { useGameLeaderboard } from '@/features/game/useGameData'
import {
  useAnnotationHistory,
  usePersonRecord,
  useResultPredictions,
  useReviewItemByPerson,
  useReviewItems,
  useReviewSummary,
} from '@/features/review/useReviewData'
import type { ReviewFilters } from '@/features/review/useReviewFilters'
import { useSessionStore } from '@/stores/session'

import { waitFor } from '../../helpers/wait'
import { item, jsonResponse } from './fixtures'

const mounted: VueWrapper[] = []
const caches: QueryClient[] = []
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  for (const cache of caches.splice(0)) cache.clear()
})

function mountPrivateReads(pending = false) {
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  caches.push(cache)
  const requests: Request[] = []
  let principal = 'account-a'
  let session!: ReturnType<typeof useSessionStore>
  let visible!: Readonly<Ref<unknown[]>>
  const selectedPerson = ref<string | null>('demo-1')
  const selectedResult = ref<string | null>('result-1')
  const snapshot = ref<string | null>('snapshot-1')
  const client = createApiClient({
    fetch: async (request) => {
      requests.push(request)
      if (pending) {
        return new Promise<Response>((_resolve, reject) => {
          request.signal.addEventListener(
            'abort',
            () => reject(new DOMException('Cancelled', 'AbortError')),
            { once: true },
          )
        })
      }
      const body =
        new URL(request.url).pathname === '/api/v1/review-items'
          ? {
              items: [item('demo-1', { surname: principal })],
              has_more: false,
              next_cursor: null,
            }
          : { owner: principal }
      return jsonResponse(body)
    },
  })
  const filters = ref<ReviewFilters>({
    queue: 'all',
    q: '',
    sort: 'tei_id',
    workflowStates: [],
    finalLabel: null,
    agreementTiers: [],
    hasAuthorityConflict: null,
    hasPredictionError: null,
    methodName: null,
    methodLabel: null,
    predictionStatus: null,
  })
  const wrapper = mount(
    defineComponent({
      setup() {
        session = useSessionStore()
        session.user = { id: principal, display_name: 'Reviewer', roles: [] }
        session.status = 'ready'
        const queries = [
          useReviewItems(ref('aggregation-1'), filters),
          useReviewSummary(ref('aggregation-1')),
          useReviewItemByPerson(ref('aggregation-1'), selectedPerson, ref(true)),
          useResultPredictions(ref('aggregation-1'), selectedResult),
          useAnnotationHistory(snapshot, selectedPerson),
          usePersonRecord(snapshot, selectedPerson),
          useGameLeaderboard(ref('project-1'), ref(10 as const), ref(true)),
        ]
        visible = computed(() => queries.map((query) => query.data.value))
        return () => h('pre', JSON.stringify(visible.value))
      },
    }),
    {
      global: {
        plugins: [createPinia(), [VueQueryPlugin, { queryClient: cache }]],
        provide: { [API_CLIENT_KEY as symbol]: client },
      },
    },
  )
  mounted.push(wrapper)
  return {
    wrapper,
    cache,
    session,
    visible,
    requests,
    selectedPerson,
    selectedResult,
    snapshot,
    switchPrincipal(id: string) {
      principal = id
      session.user = { id, display_name: 'Reviewer', roles: [] }
    },
  }
}

describe('private review and game reads', () => {
  it('hides every previous account value synchronously and fetches fresh data for the new principal', async () => {
    const context = mountPrivateReads()
    await waitFor(() => expect(context.requests).toHaveLength(7))
    await waitFor(() =>
      expect(context.visible.value.every((value) => value !== undefined)).toBe(true),
    )
    expect(context.wrapper.text()).toContain('account-a')
    context.switchPrincipal('account-b')
    // Vue query observers can still hold the old value until their next watcher flush.
    expect(context.visible.value).toEqual(Array(7).fill(undefined))
    await context.wrapper.vm.$nextTick()
    expect(context.wrapper.text()).not.toContain('account-a')
    await waitFor(() => expect(context.requests).toHaveLength(14))
    await waitFor(() => expect(context.wrapper.text()).toContain('account-b'))
    expect(context.wrapper.text()).not.toContain('account-a')
    expect(context.cache.getQueryCache().getAll()).toHaveLength(14)
    expect(
      context.cache
        .getQueryCache()
        .getAll()
        .map((query) => query.queryKey.at(-1)),
    ).toEqual([
      ...Array(7).fill({ principal_id: 'account-a' }),
      ...Array(7).fill({ principal_id: 'account-b' }),
    ])
  })

  it('aborts every in-flight private read when its owner is cancelled', async () => {
    const context = mountPrivateReads(true)
    await waitFor(() => expect(context.requests).toHaveLength(7))

    await context.cache.cancelQueries()

    expect(context.requests.every((request) => request.signal.aborted)).toBe(true)
    expect(context.visible.value).toEqual(Array(7).fill(undefined))
  })

  it('blocks every private read and hides cached values until forced password change completes', async () => {
    const context = mountPrivateReads()
    await waitFor(() => expect(context.requests).toHaveLength(7))
    await waitFor(() => expect(context.wrapper.text()).toContain('account-a'))
    context.session.mustChangePassword = true
    await flushPromises()
    expect(context.wrapper.text()).toBe('[null,null,null,null,null,null,null]')
    await context.cache.invalidateQueries()
    await flushPromises()
    expect(context.requests).toHaveLength(7)
    context.session.mustChangePassword = false
    await waitFor(() => expect(context.requests).toHaveLength(14))
    await waitFor(() => expect(context.wrapper.text()).toContain('account-a'))
  })

  it('keeps nullable person and result reads disabled after their selection is cleared', async () => {
    const context = mountPrivateReads()
    await waitFor(() => expect(context.requests).toHaveLength(7))
    context.selectedPerson.value = null
    context.selectedResult.value = null
    context.snapshot.value = null
    await flushPromises()
    await context.cache.invalidateQueries()
    await waitFor(() => expect(context.requests).toHaveLength(10))
    const visible = JSON.parse(context.wrapper.text()) as unknown[]
    expect(visible.slice(2, 6)).toEqual([null, null, null, null])
  })
})
