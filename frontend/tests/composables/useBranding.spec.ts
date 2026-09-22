import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { createApiClient, type ApiClient } from '@/api'
import { useBranding, type BrandingState, type UseBranding } from '@/composables/useBranding'

import { apiClientWithJsonResponse, apiClientWithNetworkError } from '../helpers/api'

function apiClientFailingOnce(recoveredBody: unknown): ApiClient {
  let callCount = 0
  return createApiClient({
    fetch: () => {
      callCount += 1
      if (callCount === 1) return Promise.reject(new TypeError('fetch failed'))
      return Promise.resolve(
        new Response(JSON.stringify(recoveredBody), {
          headers: { 'content-type': 'application/json' },
        }),
      )
    },
  })
}

/** `useBranding` calls `onMounted`, so it needs a real component instance to run inside. */
function mountBranding(client: Parameters<typeof useBranding>[0]) {
  let hook!: UseBranding
  const wrapper = mount(
    defineComponent({
      setup() {
        hook = useBranding(client)
        return () => null
      },
    }),
  )
  return { wrapper, hook: () => hook }
}

const FULL_RESPONSE = {
  institution_name: 'Berlin-Brandenburgische Akademie der Wissenschaften',
  institution_url: 'https://www.bbaw.de/',
  logo_url: '/api/v1/branding/logo',
  editors: ['Frederike Neuber'],
  published_since_year: 2026,
  initiatives: [{ name: 'Gender & Data', url: 'https://gender-data.bbaw.de/' }],
  contact_email: 'telota@bbaw.de',
  privacy_notice_url: 'https://www.bbaw.de/datenschutz',
  legal_entity: {
    name: 'Berlin-Brandenburgische Akademie der Wissenschaften',
    legal_form: null,
    address_lines: ['Jägerstraße 22/23', '10117 Berlin'],
    telephone: null,
    telephone_href: null,
    representative: null,
    vat_id: 'DE 167 449 058',
  },
}

describe('useBranding', () => {
  it('starts loading, then reports the fetched data', async () => {
    const { hook } = mountBranding(apiClientWithJsonResponse(FULL_RESPONSE))

    expect(hook().state.value).toEqual({ status: 'loading' })
    await flushPromises()

    const state: BrandingState = hook().state.value
    expect(state.status).toBe('ready')
    if (state.status !== 'ready') throw new Error('unreachable')
    expect(state.data.institution_name).toBe(FULL_RESPONSE.institution_name)
    expect(state.data.legal_entity?.vat_id).toBe('DE 167 449 058')
  })

  it('normalizes an unconfigured response to guaranteed empty arrays', async () => {
    const { hook } = mountBranding(apiClientWithJsonResponse({}))

    await flushPromises()

    const state = hook().state.value
    expect(state.status).toBe('ready')
    if (state.status !== 'ready') throw new Error('unreachable')
    expect(state.data.editors).toEqual([])
    expect(state.data.initiatives).toEqual([])
    expect(state.data.legal_entity).toBeNull()
    expect(state.data.institution_name).toBeNull()
  })

  it('normalizes an absent address on a configured legal entity', async () => {
    const { hook } = mountBranding(apiClientWithJsonResponse({ legal_entity: { name: 'BBAW' } }))

    await flushPromises()

    const state = hook().state.value
    expect(state.status).toBe('ready')
    if (state.status !== 'ready') throw new Error('unreachable')
    expect(state.data.legal_entity?.address_lines).toEqual([])
  })

  it('reports a network failure as an error state', async () => {
    const { hook } = mountBranding(apiClientWithNetworkError())

    await flushPromises()

    expect(hook().state.value).toEqual({ status: 'error' })
  })

  it('reports a non-success response as an error state', async () => {
    const { hook } = mountBranding(apiClientWithJsonResponse({}, { status: 500 }))

    await flushPromises()

    expect(hook().state.value).toEqual({ status: 'error' })
  })

  it('recovers from an error once refresh() succeeds', async () => {
    const { hook } = mountBranding(apiClientFailingOnce(FULL_RESPONSE))
    await flushPromises()
    expect(hook().state.value).toEqual({ status: 'error' })

    await hook().refresh()

    expect(hook().state.value.status).toBe('ready')
  })
})
