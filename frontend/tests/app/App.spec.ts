import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import { createApiClient } from '@/api'
import { createAppRouter } from '@/app/router'

import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithJsonResponse, apiClientWithRoutes } from '../helpers/api'
import { expectNoAxeViolations } from '../helpers/axe'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const
const PAGES = ['/', '/login', '/impressum', '/gibt-es-nicht'] as const

afterEach(() => {
  document.body.replaceChildren()
  delete document.documentElement.dataset.theme
  localStorage.clear()
})

describe.each(['de', 'en'] as const)('application shell in %s', (locale) => {
  it('renders the start page with its application title', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithJsonResponse({}))

    expect(wrapper.get('h1').text()).toBe(catalogues[locale].app.title)
  })

  it('bypasses navigation on successive routes without changing the URL or nesting main landmarks', async () => {
    const router = createAppRouter(createMemoryHistory())
    const wrapper = await mountApplicationAt('/', locale, apiClientWithJsonResponse({}), router)

    for (const path of ['/?context=kept', '/login?redirect=%2Fprojects']) {
      await router.push(path)
      const link = wrapper.get<HTMLAnchorElement>('a[href="#main-content"]')
      expect(link.text()).toBe(catalogues[locale].nav.skipToContent)
      expect(wrapper.element.querySelector('a[href], button, input, select, textarea')).toBe(
        link.element,
      )
      const destination = wrapper.get<HTMLElement>('#main-content')
      expect(destination.attributes('tabindex')).toBe('-1')
      expect(destination.findAll('main')).toHaveLength(1)
      expect(wrapper.findAll('main main')).toHaveLength(0)

      link.element.focus()
      await link.trigger('click')

      expect(document.activeElement).toBe(destination.element)
      expect(router.currentRoute.value.fullPath).toBe(path)
    }
    wrapper.unmount()
  })

  it.each(PAGES)('shows publication details once in the footer on %s', async (path) => {
    const wrapper = await mountApplicationAt(path, locale, apiClientWithJsonResponse({}))

    const footer = wrapper.get('.app-footer')
    const publication = footer.get('section[aria-labelledby="publication-heading"]')
    expect(publication.get('h2#publication-heading').text()).toBe(
      catalogues[locale].publication.heading,
    )
    expect(wrapper.findAll('#publication-heading')).toHaveLength(1)
    expect(wrapper.get('main').text()).not.toContain(catalogues[locale].publication.heading)
    expect(footer.text()).toContain(catalogues[locale].footer.legalNotice)
  })

  it.each(PAGES)('has one page title and no axe violations on %s', async (path) => {
    for (const theme of ['light', 'dark'] as const) {
      document.documentElement.dataset.theme = theme
      const wrapper = await mountApplicationAt(path, locale, apiClientWithJsonResponse({}))

      expect(wrapper.findAll('h1')).toHaveLength(1)
      expect(wrapper.find('aside').exists()).toBe(false)
      expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
      expect(document.querySelector('.mobile-navigation')).toBeNull()
      expect(wrapper.get('.app-header-brand').text()).toBe(catalogues[locale].app.title)
      expect(wrapper.findAll('header [aria-haspopup="listbox"]')).toHaveLength(2)
      await expectNoAxeViolations(wrapper.element)
      wrapper.unmount()
    }
  })

  it('keeps the public shell while the current session and its restrictions are still loading', async () => {
    const user = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer', roles: [] }
    let resolveMe!: (response: Response) => void
    let resolveFlags!: (response: Response) => void
    const me = new Promise<Response>((resolve) => {
      resolveMe = resolve
    })
    const flags = new Promise<Response>((resolve) => {
      resolveFlags = resolve
    })
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path === '/api/v1/me') return me
        if (path === '/api/v1/auth/session') return flags
        if (path === '/api/v1/branding') return Promise.resolve(Response.json({}))
        if (path === '/api/v1/me/preferences')
          return Promise.resolve(
            Response.json({
              locale,
              theme: 'system',
              desktop_sidebar_collapsed: false,
              revision: 1,
            }),
          )
        return Promise.resolve(Response.json({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/', locale, client)
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
    expect(document.querySelector('.mobile-navigation')).toBeNull()
    expect(wrapper.get('.app-header-brand').text()).toBe(catalogues[locale].app.title)
    expect(wrapper.findAll('header [aria-haspopup="listbox"]')).toHaveLength(2)
    resolveMe(Response.json(user))
    await flushPromises()
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
    resolveFlags(Response.json({ must_change_password: false, keep_signed_in: false }))
    await waitFor(() => expect(wrapper.find('aside').exists()).toBe(true))
    expect(wrapper.find('.app-header-brand').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(true)
    expect(wrapper.findAll('aside [aria-haspopup="listbox"]')).toHaveLength(2)
    expect(wrapper.find('header [aria-haspopup="listbox"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('restores private navigation after a successful sign-in without duplicating presentation controls', async () => {
    const wrapper = await mountApplicationAt(
      '/login',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': {
          body: { error: { code: 'authentication_required', message: 'No session.' } },
          init: { status: 401 },
        },
        '/api/v1/auth/login': {
          body: { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer', roles: [] },
        },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
        '/api/v1/me/preferences': {
          body: { locale, theme: 'system', desktop_sidebar_collapsed: false, revision: 1 },
        },
      }),
    )
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
    await wrapper.get('#login-username').setValue('reviewer')
    await wrapper.get('#login-password').setValue('correct-password')
    await wrapper.get('.login-form').trigger('submit')
    await waitFor(() => expect(wrapper.vm.$route.path).toBe('/'))
    await waitFor(() => expect(wrapper.find('aside').exists()).toBe(true))
    expect(wrapper.find('.app-header-brand').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(true)
    expect(wrapper.findAll('[data-preference="locale"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-preference="theme"]')).toHaveLength(1)
    expect(wrapper.get('aside a[href="/projects"]').text()).toBe(catalogues[locale].nav.projects)
    expect(wrapper.get('header .account-menu-button').text()).toBe('Reviewer')
    wrapper.unmount()
  })
})
