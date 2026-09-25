import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import type { UserPreferences } from '@/composables/useUserPreferences'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import type { RouteResponse } from '../helpers/api'
import { expectNoAxeViolations } from '../helpers/axe'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const
const USER = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Reviewer One',
  roles: [],
}

function preferencesClient(preferences: UserPreferences) {
  const preferenceRequests: string[] = []
  const routes: Record<string, RouteResponse> = {
    '/api/v1/branding': { body: {} },
    '/api/v1/me': { body: USER },
    '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    '/api/v1/me/preferences': { body: preferences },
    '/api/v1/projects': { body: { items: [], has_more: false, next_cursor: null } },
  }
  const client = createApiClient({
    fetch: (request) => {
      const pathname = new URL(request.url).pathname
      if (pathname === '/api/v1/me/preferences') preferenceRequests.push(request.method)
      const route = routes[pathname]
      return Promise.resolve(
        new Response(JSON.stringify(route?.body ?? {}), {
          status: route ? 200 : 404,
          headers: { 'content-type': 'application/json' },
        }),
      )
    },
  })
  return { client, preferenceRequests }
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('saved sidebar presentation in %s', (locale: AppLocale) => {
  it.each(['light', 'dark'] as const)(
    'applies the saved collapse with labelled, keyboard-focusable navigation in %s',
    async (theme) => {
      const { client, preferenceRequests } = preferencesClient({
        locale,
        theme,
        desktop_sidebar_collapsed: true,
        revision: 3,
      })
      const wrapper = await mountApplicationAt('/projects', locale, client)
      await waitFor(() => {
        expect(wrapper.get('aside').classes()).toContain('app-sidebar--desktop-collapsed')
        expect(document.documentElement.dataset.theme).toBe(theme)
      })

      const projects = wrapper.get<HTMLAnchorElement>('aside a[href="/projects"]')
      expect(projects.text()).toBe(catalogues[locale].nav.projects)
      expect(projects.attributes('title')).toBeUndefined()
      expect(projects.attributes('aria-current')).toBe('page')
      expect(projects.attributes('aria-hidden')).toBeUndefined()
      expect(projects.element.tabIndex).toBe(0)
      projects.element.focus()
      expect(document.activeElement).toBe(projects.element)
      await flushPromises()
      const tooltip = document.getElementById(projects.attributes('aria-describedby') ?? '')
      expect(tooltip?.getAttribute('role')).toBe('tooltip')
      expect(tooltip?.textContent).toBe(catalogues[locale].nav.projects)
      const settings = wrapper.get<HTMLAnchorElement>('aside footer a[href="/settings"]')
      expect(settings.text()).toBe(catalogues[locale].header.settings)
      expect(settings.classes()).toContain('nav-item--desktop-collapsed')
      settings.element.focus()
      expect(document.activeElement).toBe(settings.element)
      await flushPromises()
      const settingsTooltip = document.getElementById(settings.attributes('aria-describedby') ?? '')
      expect(settingsTooltip?.textContent).toBe(catalogues[locale].header.settings)
      expect(wrapper.get('aside nav').attributes('aria-label')).toBe(catalogues[locale].nav.label)
      await expectNoAxeViolations(wrapper.get('aside').element)
      expect(preferenceRequests).toEqual(['GET'])
      wrapper.unmount()
    },
  )
})

describe('responsive sidebar state separation', () => {
  it.each([false, true])(
    'retains saved desktop collapse %s while crossing narrow and desktop widths without saving',
    async (collapsed) => {
      const { client, preferenceRequests } = preferencesClient({
        locale: 'en',
        theme: 'system',
        desktop_sidebar_collapsed: collapsed,
        revision: 4,
      })
      vi.stubGlobal('innerWidth', 1440)
      const wrapper = await mountApplicationAt('/projects', 'en', client)
      await waitFor(() => {
        expect(preferenceRequests).toEqual(['GET'])
        expect(wrapper.find('aside a[href="/projects"]').exists()).toBe(true)
      })
      await flushPromises()

      // jsdom has no layout engine. This checks that viewport events never mutate the saved
      // desktop state; actual rail geometry is part of the browser layout verification.
      for (const width of [1079, 375, 1080, 1440]) {
        vi.stubGlobal('innerWidth', width)
        window.dispatchEvent(new Event('resize'))
        await flushPromises()
        expect(wrapper.get('aside').classes().includes('app-sidebar--desktop-collapsed')).toBe(
          collapsed,
        )
        expect(wrapper.get('aside a[href="/projects"]').text()).toBe(en.nav.projects)
      }
      expect(preferenceRequests).toEqual(['GET'])
      wrapper.unmount()
    },
  )
})
