import { DOMWrapper, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import { createAppRouter } from '@/app/router'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const
const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Drawer user', roles: [] }
const PROJECT = 'b0000000-0000-0000-0000-000000000001'
const mounted: VueWrapper[] = []

class ResponsiveQuery extends EventTarget implements MediaQueryList {
  matches: boolean
  media: string
  onchange: ((this: MediaQueryList, event: MediaQueryListEvent) => unknown) | null = null

  constructor(query: string) {
    super()
    this.media = query
    this.matches = query === '(width < 720px)'
  }

  addListener(): void {
    // Components use the modern event-listener API.
  }

  removeListener(): void {
    // Components use the modern event-listener API.
  }

  setMatches(matches: boolean): void {
    this.matches = matches
    this.dispatchEvent(Object.assign(new Event('change'), { matches, media: this.media }))
  }
}

function bodyGet(selector: string): DOMWrapper<Element> {
  const element = document.querySelector(selector)
  if (element === null) throw new Error(`Missing drawer element: ${selector}`)
  return new DOMWrapper(element)
}

function dialog(): HTMLElement | null {
  return document.querySelector('[role="dialog"].mobile-navigation')
}

async function application(
  locale: AppLocale,
  options: { path?: string; state?: 'ready' | 'signedOut' | 'passwordChange' } = {},
) {
  const media = new Map<string, ResponsiveQuery>()
  vi.stubGlobal('matchMedia', (query: string) => {
    if (!media.has(query)) media.set(query, new ResponsiveQuery(query))
    return media.get(query)!
  })
  vi.stubGlobal('innerWidth', 375)
  const preferenceRequests: string[] = []
  const client = createApiClient({
    fetch: (request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/v1/me' && options.state === 'signedOut') {
        return Promise.resolve(
          Response.json(
            { error: { code: 'authentication_required', message: 'No session.' } },
            { status: 401 },
          ),
        )
      }
      if (path === '/api/v1/me/preferences') preferenceRequests.push(request.method)
      const responses: Record<string, unknown> = {
        '/api/v1/branding': {},
        '/api/v1/me': USER,
        '/api/v1/auth/session': {
          must_change_password: options.state === 'passwordChange',
          keep_signed_in: false,
        },
        '/api/v1/me/preferences': {
          locale,
          theme: 'system',
          desktop_sidebar_collapsed: true,
          revision: 2,
        },
        '/api/v1/projects': { items: [], has_more: false, next_cursor: null },
        [`/api/v1/projects/${PROJECT}`]: {
          id: PROJECT,
          slug: 'project-a',
          display_name: 'Project A',
          current_user_role: 'viewer',
          working_aggregation_execution_id: null,
          created_at: '2026-01-01T00:00:00Z',
        },
      }
      return Promise.resolve(
        Response.json(responses[path] ?? {}, { status: path in responses ? 200 : 404 }),
      )
    },
  })
  const router = createAppRouter(createMemoryHistory())
  const wrapper = await mountApplicationAt(options.path ?? '/projects', locale, client, router)
  mounted.push(wrapper)
  await waitFor(() => {
    expect(wrapper.find('.app-header-session').exists()).toBe(true)
    if (options.state !== 'signedOut' && options.state !== 'passwordChange') {
      expect(preferenceRequests).toContain('GET')
    }
  })
  const trigger = wrapper.get<HTMLButtonElement>('.app-header-navigation')
  async function open() {
    trigger.element.focus()
    await trigger.trigger('click')
    await waitFor(() => expect(dialog()).not.toBeNull())
    return bodyGet('[role="dialog"].mobile-navigation')
  }
  return { wrapper, router, trigger, open, media, preferenceRequests }
}

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.replaceChildren()
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe.each(['de', 'en'] as const)('mobile navigation in %s', (locale: AppLocale) => {
  const messages = catalogues[locale]

  it('opens a named modal from the named header trigger and moves focus into it', async () => {
    const { trigger, open } = await application(locale)
    expect(trigger.attributes('aria-label')).toBe(messages.nav.openNavigation)
    expect(trigger.attributes('aria-haspopup')).toBe('dialog')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    const drawer = await open()
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(drawer.attributes('aria-modal')).toBe('true')
    const title = document.getElementById(drawer.attributes('aria-labelledby') ?? '')
    expect(title?.textContent).toBe(messages.nav.label)
    expect(drawer.get('aside').classes()).toContain('app-sidebar--mobile')
    expect(drawer.get('a[href="/projects"]').text()).toBe(messages.nav.projects)
    expect(drawer.get('a[href="/projects"]').classes()).toContain('nav-item--mobile')
    expect(drawer.find('.sidebar-collapse-button').exists()).toBe(false)
    await waitFor(() => expect(drawer.element.contains(document.activeElement)).toBe(true))
  })

  it.each(['Escape', 'close button', 'backdrop'] as const)(
    'closes with %s and restores focus to the header trigger',
    async (method) => {
      const { trigger, open } = await application(locale)
      await open()
      await waitFor(() => expect(dialog()?.contains(document.activeElement)).toBe(true))
      if (method === 'Escape') {
        document.activeElement?.dispatchEvent(
          new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
        )
      } else if (method === 'close button') {
        const close = bodyGet('.mobile-navigation-close')
        expect(close.attributes('aria-label')).toBe(messages.nav.closeNavigation)
        await close.trigger('click')
      } else {
        const backdrop = bodyGet('.mobile-navigation-backdrop')
        await backdrop.trigger('mousedown')
        await backdrop.trigger('click')
      }
      await waitFor(() => expect(dialog()).toBeNull())
      expect(trigger.attributes('aria-expanded')).toBe('false')
      await waitFor(() => expect(document.activeElement).toBe(trigger.element))
    },
  )

  it('opens personal settings from the drawer footer and closes after navigation', async () => {
    const { router, trigger, open } = await application(locale)
    const drawer = await open()
    const settings = drawer.get('footer a[href="/settings"]')
    expect(settings.text()).toBe(messages.header.settings)
    expect(settings.classes()).toContain('nav-item--mobile')
    await settings.trigger('click')
    await waitFor(() => expect(router.currentRoute.value.name).toBe('userSettings'))
    expect(
      bodyGet('.app-shell > aside footer a[href="/settings"]').attributes('aria-current'),
    ).toBe('page')
    await waitFor(() => expect(dialog()).toBeNull())
    expect(trigger.attributes('aria-expanded')).toBe('false')
  })

  it('keeps the drawer open when a route guard cancels navigation', async () => {
    const { router, trigger, open } = await application(locale)
    const guard = vi.fn(() => false)
    const removeGuard = router.beforeEach(guard)
    const drawer = await open()
    await drawer.get('a.app-sidebar-brand').trigger('click')
    await waitFor(() => expect(guard).toHaveBeenCalled())
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('projects')
    expect(dialog()).not.toBeNull()
    expect(trigger.attributes('aria-expanded')).toBe('true')
    removeGuard()
  })

  it('moves focus to the persistent current destination across the breakpoint without saving preferences', async () => {
    const { wrapper, trigger, open, media, preferenceRequests } = await application(locale)
    const current = wrapper.get('aside a[aria-current="page"]')
    await open()
    await waitFor(() => expect(dialog()?.contains(document.activeElement)).toBe(true))
    vi.stubGlobal('innerWidth', 1080)
    media.get('(width < 720px)')!.setMatches(false)
    await waitFor(() => expect(dialog()).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(current.element))
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('aside').classes()).toContain('app-sidebar--desktop-collapsed')
    expect(preferenceRequests.every((method) => method === 'GET')).toBe(true)
  })

  it('moves focus to the persistent brand when leaving mobile navigation on a public page', async () => {
    const { wrapper, open, media, preferenceRequests } = await application(locale, {
      path: '/',
      state: 'signedOut',
    })
    const brand = wrapper.get('aside a.app-sidebar-brand')
    await open()
    await waitFor(() => expect(dialog()?.contains(document.activeElement)).toBe(true))
    vi.stubGlobal('innerWidth', 1080)
    media.get('(width < 720px)')!.setMatches(false)
    await waitFor(() => expect(dialog()).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(brand.element))
    expect(preferenceRequests).toEqual([])
  })

  it('shows the same viewer destinations as the persistent navigation', async () => {
    const { wrapper, open } = await application(locale, { path: `/projects/${PROJECT}/overview` })
    await waitFor(() => expect(wrapper.get('aside').text()).toContain(messages.nav.currentProject))
    const persistentItems = wrapper.findAll('aside nav .nav-item').map((item) => item.text())
    const drawer = await open()
    expect(drawer.findAll('nav .nav-item').map((item) => item.text())).toEqual(persistentItems)
    expect(persistentItems).toContain(messages.nav.annotate)
    expect(persistentItems).not.toContain(messages.nav.import)
    expect(persistentItems).not.toContain(messages.nav.review)
  })

  it.each(['signedOut', 'passwordChange'] as const)(
    'keeps the brand and preferences but hides private links for %s',
    async (state) => {
      const { open, preferenceRequests } = await application(locale, { path: '/', state })
      const drawer = await open()
      expect(drawer.get('.app-sidebar-brand').text()).toBe(messages.app.title)
      expect(drawer.find('.sidebar-preferences').exists()).toBe(true)
      expect(drawer.find('nav').exists()).toBe(false)
      expect(preferenceRequests).toEqual([])
    },
  )
})
