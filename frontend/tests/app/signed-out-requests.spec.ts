import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'

import { jsonResponse } from '../features/review/fixtures'
import { SCREENS } from '../accessibility/mockApi'
import { mountApplicationAt } from '../helpers/render'

/**
 * A visitor without a session is about to be sent to /login. Until the session is known, and after it
 * is known to be absent, a screen must ask the API for nothing but the session itself: a deep link
 * would otherwise fire a burst of requests that can only fail (found in the browser at M9, where the
 * placeholder ids of a smoke test even came back as 422).
 */
const SESSION_ENDPOINTS = new Set(['/api/v1/branding', '/api/v1/me', '/api/v1/auth/session'])

afterEach(() => {
  document.body.replaceChildren()
})

describe('screens for a visitor without a session', () => {
  it.each(Object.entries(SCREENS))('%s requests nothing but the session', async (_name, path) => {
    const requested: string[] = []
    const client = createApiClient({
      fetch: async (request) => {
        const { pathname } = new URL(request.url)
        requested.push(pathname)
        if (pathname === '/api/v1/branding') return jsonResponse({})
        return jsonResponse(
          {
            error: { code: 'authentication_required', message: 'no', details: {}, request_id: 'r' },
          },
          { status: 401 },
        )
      },
    })

    const wrapper = await mountApplicationAt(path, 'en', client)
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    await flushPromises()

    expect(requested.filter((pathname) => !SESSION_ENDPOINTS.has(pathname))).toEqual([])
    wrapper.unmount()
  })
})
