import { DOMWrapper, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

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

  it('uses the main home sign-in action and restores the header link on other public pages', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))
    await flushPromises()

    expect(wrapper.find('header a[href="/login"]').exists()).toBe(false)
    expect(wrapper.get('main a[href="/login"]').text()).toBe(catalogues[locale].home.guest.signIn)
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
    expect(wrapper.get('.app-header-brand').attributes('href')).toBe('/')
    expect(wrapper.findAll('a[href="/login"]')).toHaveLength(1)

    await wrapper.vm.$router.push('/impressum')
    await waitFor(() => expect(wrapper.get('header a[href="/login"]').text()).toBe(messages.signIn))
    await wrapper.vm.$router.push('/')
    await waitFor(() => expect(wrapper.find('main a[href="/login"]').exists()).toBe(true))
    expect(wrapper.find('header a[href="/login"]').exists()).toBe(false)
    expect(wrapper.findAll('a[href="/login"]')).toHaveLength(1)
    wrapper.unmount()
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

    expect(wrapper.find('aside').exists()).toBe(true)
    expect(wrapper.find('.app-header-brand').exists()).toBe(false)
    expect(wrapper.find('header [aria-haspopup="listbox"]').exists()).toBe(false)
    expect(wrapper.get('header .account-menu-button').text()).toBe('Reviewer One')
    await wrapper.get('header .account-menu-button').trigger('click')
    expect(wrapper.get('header button[role="menuitem"]').text()).toBe(messages.signOut)
    expect(wrapper.get('header a[href="/settings"]').text()).toBe(messages.settings)
    expect(wrapper.find('aside footer a[href="/settings"]').exists()).toBe(false)
    expect(wrapper.find('.app-header-switcher--locale').exists()).toBe(false)
    expect(wrapper.find('.app-header-switcher--theme').exists()).toBe(false)
  })

  it('closes the account menu and restores its trigger after cancelling navigation with a draft', async () => {
    const wrapper = await mountApplicationAt(
      '/admin/users',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': { body: { ...USER, roles: ['admin'] } },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
        '/api/v1/admin/users': { body: { items: [], has_more: false, next_cursor: null } },
      }),
    )
    await waitFor(() => expect(wrapper.find('#admin-user-create-display-name').exists()).toBe(true))
    await wrapper.get('#admin-user-create-display-name').setValue('Unsaved account')
    const trigger = wrapper.get<HTMLButtonElement>('header .account-menu-button')
    trigger.element.focus()
    await trigger.trigger('click')
    await wrapper.get('header a[href="/settings"]').trigger('click')
    await waitFor(() =>
      expect(new DOMWrapper(document.body).find('[role="dialog"]').exists()).toBe(true),
    )
    expect(wrapper.find('header [role="menu"]').exists()).toBe(false)
    const dialog = new DOMWrapper(document.body).get('[role="dialog"]')
    await waitFor(() => expect(dialog.element.contains(document.activeElement)).toBe(true))
    const stay = dialog
      .findAll('button')
      .find((button) => button.text() === catalogues[locale].draftNavigation.stay)
    await stay?.trigger('click')
    await waitFor(() =>
      expect(new DOMWrapper(document.body).find('[role="dialog"]').exists()).toBe(false),
    )

    expect(wrapper.vm.$router.currentRoute.value.path).toBe('/admin/users')
    expect(wrapper.get<HTMLInputElement>('#admin-user-create-display-name').element.value).toBe(
      'Unsaved account',
    )
    expect(wrapper.find('header [role="menu"]').exists()).toBe(false)
    await waitFor(() => expect(document.activeElement).toBe(trigger.element))
    wrapper.unmount()
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
    await wrapper.get('header .account-menu-button').trigger('click')
    expect(wrapper.find('a[href="/settings"]').exists()).toBe(false)
    expect(wrapper.get('header button[role="menuitem"]').text()).toBe(messages.signOut)
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
    expect(wrapper.findAll('header [aria-haspopup="listbox"]')).toHaveLength(2)
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

    await wrapper.get('header .account-menu-button').trigger('click')
    await wrapper.get('header button[role="menuitem"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('header a[href="/login"]').exists()).toBe(false)
    expect(wrapper.get('main a[href="/login"]').text()).toBe(catalogues[locale].home.guest.signIn)
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
    expect(wrapper.get('.app-header-brand').text()).toBe(catalogues[locale].app.title)
    expect(wrapper.findAll('header [aria-haspopup="listbox"]')).toHaveLength(2)
  })

  it('keeps anonymous presentation controls reachable in the header without a sidebar', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))
    await flushPromises()
    expect(wrapper.find('header a[href="/login"]').exists()).toBe(false)
    expect(wrapper.get('main a[href="/login"]').text()).toBe(catalogues[locale].home.guest.signIn)
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.findAll('header [aria-haspopup="listbox"]')).toHaveLength(2)
    expect(wrapper.get('header [data-preference="locale"] button').attributes('aria-label')).toBe(
      catalogues[locale].locale.label,
    )
    await wrapper.get('header [data-preference="theme"] button').trigger('click')
    const dark = wrapper
      .findAll('header [role="option"]')
      .find((option) => option.text() === catalogues[locale].theme.dark)
    expect(dark).toBeDefined()
    await dark!.trigger('click')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('gendertagger.theme')).toBe('dark')
    expect(wrapper.get('.app-footer a[href="/impressum"]').text()).toBe(
      catalogues[locale].footer.legalNotice,
    )
    wrapper.unmount()
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
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
    expect(wrapper.findAll('header [aria-haspopup="listbox"]')).toHaveLength(2)
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

    await wrapper.get('header .account-menu-retry').trigger('click')
    await flushPromises()

    expect(wrapper.find('header a[href="/login"]').exists()).toBe(false)
    expect(wrapper.get('main a[href="/login"]').text()).toBe(catalogues[locale].home.guest.signIn)
    expect(wrapper.find('aside footer a[href="/settings"]').exists()).toBe(false)
  })
})
