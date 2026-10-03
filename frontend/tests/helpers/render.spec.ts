import type { QueryClient } from '@tanstack/vue-query'
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import * as queryClientModule from '@/app/queryClient'

import { mountApplicationAt } from './render'

describe('application fixture teardown', () => {
  const resources: { queryClient: QueryClient; signals: AbortSignal[] }[] = []

  beforeEach(() => {
    expect(document.querySelector('.app-shell')).toBeNull()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  afterAll(() => {
    // Includes the application deliberately left mounted by the automatic-teardown case.
    expect(document.querySelector('.app-shell')).toBeNull()
    for (const { queryClient, signals } of resources) {
      expect(queryClient.getQueryCache().getAll()).toEqual([])
      expect(signals.every((signal) => signal.aborted)).toBe(true)
    }
  })

  async function mountWithPendingBranding() {
    const queryClient = queryClientModule.createQueryClient()
    vi.spyOn(queryClientModule, 'createQueryClient').mockReturnValue(queryClient)
    const signals: AbortSignal[] = []
    resources.push({ queryClient, signals })
    const client = createApiClient({
      fetch: (request) => {
        if (new URL(request.url).pathname === '/api/v1/branding') {
          signals.push(request.signal)
          return new Promise<Response>((_resolve, reject) => {
            request.signal.addEventListener('abort', () =>
              reject(new DOMException('', 'AbortError')),
            )
          })
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({ error: { code: 'authentication_required', message: 'Sign in.' } }),
            { status: 401, headers: { 'content-type': 'application/json' } },
          ),
        )
      },
    })
    const wrapper = await mountApplicationAt('/', 'en', client)
    expect(signals).not.toHaveLength(0)
    expect(queryClient.getQueryCache().getAll()).not.toHaveLength(0)
    return { wrapper, queryClient, signals }
  }

  it('cancels pending requests and releases cached data when explicitly unmounted twice', async () => {
    const { wrapper, queryClient, signals } = await mountWithPendingBranding()
    const warn = vi.spyOn(console, 'warn')

    wrapper.unmount()
    wrapper.unmount()

    expect(signals.every((signal) => signal.aborted)).toBe(true)
    expect(queryClient.getQueryCache().getAll()).toEqual([])
    expect(warn).not.toHaveBeenCalled()
  })

  it('owns applications that the test leaves mounted', async () => {
    const { wrapper } = await mountWithPendingBranding()

    expect(wrapper.find('.app-shell').exists()).toBe(true)
  })
})
