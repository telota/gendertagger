import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { mountApplicationAt } from '../helpers/render'

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

  it('always links the brand to the start page', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))

    const brand = wrapper.get('header a[href="/"]')
    expect(brand.text()).toBe(catalogues[locale].app.title)
  })

  it('offers a sign-in link when signed out', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))
    await flushPromises()

    expect(wrapper.get('header a[href="/login"]').text()).toBe(messages.signIn)
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
  })

  it('switches the interface language when a different option is picked', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))
    await flushPromises()
    const other: AppLocale = locale === 'de' ? 'en' : 'de'
    const otherLabel = other === 'de' ? 'Deutsch' : 'English'

    const localeSwitcher = wrapper.get('.app-header-switcher--locale')
    await localeSwitcher.get('button').trigger('click')
    const option = localeSwitcher.findAll('li').find((item) => item.text() === otherLabel)
    await option?.trigger('click')
    await flushPromises()

    expect(wrapper.get('header a[href="/login"]').text()).toBe(catalogues[other].header.signIn)
  })

  it('switches the document theme when a different option is picked', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))
    await flushPromises()
    const darkLabel = catalogues[locale].theme.dark

    const themeSwitcher = wrapper.get('.app-header-switcher--theme')
    await themeSwitcher.get('button').trigger('click')
    const option = themeSwitcher.findAll('li').find((item) => item.text() === darkLabel)
    await option?.trigger('click')
    await flushPromises()

    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})
