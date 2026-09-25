import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { mountApplicationAt } from '../helpers/render'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

const catalogues = { de, en } as const

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const NOT_SIGNED_IN: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': {
    body: { error: { code: 'authentication_required', message: 'Authentication is required.' } },
    init: { status: 401 },
  },
}

afterEach(() => {
  document.body.replaceChildren()
  localStorage.clear()
  delete document.documentElement.dataset.theme
})

describe.each(['de', 'en'] as const)('AppHeader in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].header

  it('offers a sign-in link when signed out', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))
    await flushPromises()

    expect(wrapper.get('header a[href="/login"]').text()).toBe(messages.signIn)
    expect(wrapper.find('aside footer a[href="/settings"]').exists()).toBe(false)
  })

  it('names the signed-in user and offers to sign out', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
      }),
    )
    await flushPromises()

    expect(wrapper.get('header').text()).toContain(
      messages.signedInAs.replace('{name}', 'Reviewer One'),
    )
    expect(wrapper.get('header .app-header-signout').text()).toBe(messages.signOut)
    expect(wrapper.find('header a[href="/settings"]').exists()).toBe(false)
    expect(wrapper.get('aside footer a[href="/settings"]').text()).toBe(messages.settings)
    expect(wrapper.find('.app-header-switcher--locale').exists()).toBe(false)
    expect(wrapper.find('.app-header-switcher--theme').exists()).toBe(false)
  })

  it('withholds account settings while a password change is required', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: true, keep_signed_in: false } },
      }),
    )
    await flushPromises()
    expect(wrapper.find('a[href="/settings"]').exists()).toBe(false)
    expect(wrapper.find('.app-header-switcher--locale').exists()).toBe(false)
  })

  it('signs out and returns to a signed-out header', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
        '/api/v1/auth/logout': { body: null, init: { status: 204 } },
      }),
    )
    await flushPromises()

    await wrapper.get('header .app-header-signout').trigger('click')
    await flushPromises()

    expect(wrapper.get('header a[href="/login"]').text()).toBe(messages.signIn)
    expect(wrapper.find('aside footer a[href="/settings"]').exists()).toBe(false)
  })

  it('keeps account actions in the header and presentation controls in the sidebar', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))
    await flushPromises()
    expect(wrapper.get('header a[href="/login"]').text()).toBe(messages.signIn)
    expect(wrapper.find('aside footer a[href="/settings"]').exists()).toBe(false)
    expect(wrapper.find('header [aria-haspopup="listbox"]').exists()).toBe(false)
    expect(wrapper.findAll('aside [aria-haspopup="listbox"]')).toHaveLength(2)
  })

  it('shows a server-error state, distinct from signed-out, when the session cannot be checked', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': {
          body: { error: { code: 'internal_error', message: 'Something went wrong.' } },
          init: { status: 500 },
        },
      }),
    )
    await flushPromises()

    expect(wrapper.get('header').text()).toContain(messages.serverError)
    expect(wrapper.find('header a[href="/login"]').exists()).toBe(false)
  })

  it('retries after a server error and recovers into the ordinary signed-out state', async () => {
    let meAttempts = 0
    const client = createApiClient({
      fetch: (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') {
          meAttempts += 1
          return Promise.resolve(
            meAttempts === 1
              ? jsonResponse(
                  { error: { code: 'internal_error', message: 'Something went wrong.' } },
                  { status: 500 },
                )
              : jsonResponse(
                  { error: { code: 'authentication_required', message: 'Gone.' } },
                  { status: 401 },
                ),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/', locale, client)
    await flushPromises()
    expect(wrapper.get('header').text()).toContain(messages.serverError)

    await wrapper.get('header .app-header-retry').trigger('click')
    await flushPromises()

    expect(wrapper.get('header a[href="/login"]').text()).toBe(messages.signIn)
    expect(wrapper.find('aside footer a[href="/settings"]').exists()).toBe(false)
  })
})
