import { isCancelledError, VueQueryPlugin } from '@tanstack/vue-query'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient, unwrap } from '@/api'
import { createQueryClient } from '@/app/queryClient'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { usePrivateCacheLifecycle } from '@/composables/usePrivateCacheLifecycle'
import { useSessionStore } from '@/stores/session'

const USER_A = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Account A', roles: [] }
const USER_B = { id: 'a0000000-0000-0000-0000-000000000002', display_name: 'Account B', roles: [] }
const PRIVATE_KEY = ['exports', 'private-export', { principal_id: USER_A.id }] as const
const BRANDING = { application_title: 'Public title' }

enableAutoUnmount(afterEach)
const caches = new Set<ReturnType<typeof createQueryClient>>()
afterEach(() => {
  for (const cache of caches) cache.clear()
  caches.clear()
})

async function mountLifecycle(privateFetch?: (request: Request) => Promise<Response>) {
  const cache = createQueryClient()
  caches.add(cache)
  const client = createApiClient({
    fetch: async (request) => {
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/me') return Response.json(USER_A)
      if (pathname === '/api/v1/auth/session') {
        return Response.json({ must_change_password: false, keep_signed_in: false })
      }
      if (pathname === '/api/v1/auth/login') {
        const { username } = (await request.json()) as { username: string }
        return Response.json(username === 'b' ? USER_B : USER_A)
      }
      if (pathname === '/api/v1/auth/logout') return new Response(null, { status: 204 })
      if (privateFetch) return privateFetch(request)
      return Response.json({}, { status: 404 })
    },
  })
  let session!: ReturnType<typeof useSessionStore>
  const wrapper = mount(
    defineComponent({
      setup() {
        session = useSessionStore()
        usePrivateCacheLifecycle()
        return () => null
      },
    }),
    {
      global: {
        plugins: [createPinia(), [VueQueryPlugin, { queryClient: cache }]],
        provide: { [API_CLIENT_KEY as symbol]: client },
      },
    },
  )
  await session.initialize()
  cache.setQueryData(['branding'], BRANDING)
  return { cache, client, session, wrapper }
}

describe('usePrivateCacheLifecycle', () => {
  it.each(['replacement', 'logout'] as const)(
    'retains public branding and destroys private read and mutation results on %s',
    async (transition) => {
      const { cache, session } = await mountLifecycle()
      cache.setQueryData(PRIVATE_KEY, { provenance: 'private-a-provenance' })
      const mutation = cache.getMutationCache().build(cache, {
        mutationKey: ['create-export'],
        mutationFn: async () => ({ id: 'private-a-result' }),
      })
      await mutation.execute(undefined)
      expect(cache.getMutationCache().getAll()[0]?.state.data).toEqual({ id: 'private-a-result' })

      if (transition === 'replacement') {
        await session.login({ username: 'b', password: 'secret', keepSignedIn: false })
      } else {
        await session.logout()
      }

      expect(cache.getQueryData(['branding'])).toEqual(BRANDING)
      expect(cache.getQueryData(PRIVATE_KEY)).toBeUndefined()
      expect(cache.getQueryCache().getAll()).toHaveLength(1)
      expect(cache.getMutationCache().getAll()).toEqual([])
    },
  )

  it('keeps the same account’s private read and mutation results during recovery', async () => {
    const { cache, session } = await mountLifecycle()
    const privateData = { provenance: 'private-a-provenance' }
    cache.setQueryData(PRIVATE_KEY, privateData)
    const mutation = cache.getMutationCache().build(cache, {
      mutationKey: ['create-export'],
      mutationFn: async () => ({ id: 'private-a-result' }),
    })
    await mutation.execute(undefined)
    const revision = session.principalRevision

    await session.login({ username: 'a', password: 'secret', keepSignedIn: false })

    expect(session.principalRevision).toBe(revision)
    expect(cache.getQueryData(['branding'])).toEqual(BRANDING)
    expect(cache.getQueryData(PRIVATE_KEY)).toEqual(privateData)
    expect(cache.getMutationCache().getAll()).toEqual([mutation])
  })

  it.each(['replacement', 'logout'] as const)(
    'cancels private transport on %s and ignores a late response without restoring its entry',
    async (transition) => {
      let finishResponse!: (response: Response) => void
      let markDispatched!: (request: Request) => void
      const dispatched = new Promise<Request>((resolve) => {
        markDispatched = resolve
      })
      const response = new Promise<Response>((resolve) => {
        finishResponse = resolve
      })
      const { cache, client, session } = await mountLifecycle((request) => {
        markDispatched(request)
        // A custom transport may finish after abort; the query layer must still discard its body.
        return response
      })
      const read = cache
        .fetchQuery({
          queryKey: PRIVATE_KEY,
          queryFn: ({ signal }) => unwrap(client.GET('/api/v1/projects', { signal })),
        })
        .catch((error: unknown) => error)
      const request = await dispatched

      if (transition === 'replacement') {
        await session.login({ username: 'b', password: 'secret', keepSignedIn: false })
      } else {
        await session.logout()
      }
      expect(request.signal.aborted).toBe(true)
      expect(isCancelledError(await read)).toBe(true)
      finishResponse(Response.json({ items: [{ display_name: 'private-a-late' }] }))
      await flushPromises()

      expect(cache.getQueryState(PRIVATE_KEY)).toBeUndefined()
      expect(cache.getQueryCache().getAll()).toHaveLength(1)
      expect(cache.getQueryData(['branding'])).toEqual(BRANDING)
    },
  )
})
