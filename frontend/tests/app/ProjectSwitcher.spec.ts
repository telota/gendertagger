import { DOMWrapper, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import type { AccessibleProject } from '@/features/projects/useProjects'
import { createAppRouter } from '@/app/router'
import { useSessionRecovery } from '@/composables/useSessionRecovery'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { expectNoAxeViolations } from '../helpers/axe'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const
const mounted: VueWrapper[] = []

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const PROJECT_A = 'b0000000-0000-0000-0000-000000000001'
const PROJECT_B = 'b0000000-0000-0000-0000-000000000002'
const project = (id: string, name: string): AccessibleProject => ({
  id,
  slug: name.toLowerCase().replace(' ', '-'),
  display_name: name,
  current_user_role: 'operator',
  current_user_can_manage_members: false,
  game_mode_enabled: false,
  manager_user_id: USER.id,
  created_by_user_id: USER.id,
  team: {
    id: 'c0000000-0000-0000-0000-000000000001',
    slug: 'editorial-team',
    display_name: 'Editorial team',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  created_at: '2026-01-01T00:00:00Z',
})
const ROUTES: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': { body: USER },
  '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
  '/api/v1/projects': {
    body: {
      items: [project(PROJECT_A, 'Project A'), project(PROJECT_B, 'Project B')],
      has_more: false,
      next_cursor: null,
    },
  },
  [`/api/v1/projects/${PROJECT_A}`]: { body: project(PROJECT_A, 'Project A') },
  [`/api/v1/projects/${PROJECT_B}`]: { body: project(PROJECT_B, 'Project B') },
}

class BreakpointQuery extends EventTarget implements MediaQueryList {
  matches = false
  onchange: ((this: MediaQueryList, event: MediaQueryListEvent) => unknown) | null = null

  constructor(public media = '(width < 720px)') {
    super()
  }

  addListener(): void {
    // The application uses addEventListener.
  }

  removeListener(): void {
    // The application uses removeEventListener.
  }

  setMatches(matches: boolean): void {
    this.matches = matches
    this.dispatchEvent(Object.assign(new Event('change'), { matches, media: this.media }))
  }
}

function projectMenu(): DOMWrapper<HTMLElement> {
  const menu = document.querySelector<HTMLElement>('.project-switcher-items')
  if (menu === null) throw new Error('Project menu is not open')
  return new DOMWrapper(menu)
}

afterEach(() => {
  useSessionRecovery().resolve()
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  localStorage.clear()
  document.body.replaceChildren()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe.each(['de', 'en'] as const)('ProjectSwitcher in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projectSwitcher

  it('is not offered without a session', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': {
          body: { error: { code: 'authentication_required', message: 'No session.' } },
          init: { status: 401 },
        },
      }),
    )
    mounted.push(wrapper)
    await flushPromises()

    expect(wrapper.find('.project-switcher').exists()).toBe(false)
  })

  it.each(['/projects', '/settings'])(
    'offers Projects instead of switching on %s',
    async (path) => {
      const wrapper = await mountApplicationAt(path, locale, apiClientWithRoutes(ROUTES))
      mounted.push(wrapper)
      await waitFor(() => expect(wrapper.find('aside a[href="/projects"]').exists()).toBe(true))
      expect(wrapper.find('.project-switcher').exists()).toBe(false)
      expect(wrapper.find('aside a[href="/settings"]').exists()).toBe(false)
    },
  )

  it('names the current project, lists the projects and marks the current one', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes(ROUTES),
    )
    mounted.push(wrapper)
    await waitFor(() => {
      expect(wrapper.get('aside .project-switcher-current').text()).toBe('Project A')
    })
    const button = wrapper.get('aside .project-switcher-button')
    expect(button.text()).toBe('Project A')
    expect(wrapper.findAll('aside .project-switcher-current')).toHaveLength(1)
    expect(button.element.closest('.app-sidebar-section')?.querySelector('h2')).toBeNull()
    expect(button.attributes('aria-label')).toBe(
      messages.currentLabel.replace('{project}', 'Project A'),
    )
    const overview = wrapper.get(`aside a[href="/projects/${PROJECT_A}/overview"]`)
    expect(
      button.element.compareDocumentPosition(overview.element) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).not.toBe(0)

    await wrapper.get('aside .project-switcher-button').trigger('click')
    await waitFor(() =>
      expect(document.querySelector('.project-switcher-items [role="menuitem"]') !== null).toBe(
        true,
      ),
    )

    // The Headless UI component stays mounted while closed; opening must position its new DOM.
    await waitFor(() =>
      expect(parseFloat(projectMenu().element.style.maxHeight)).toBeGreaterThan(0),
    )

    const items = projectMenu().findAll('[role="menuitem"]')
    expect(items.map((item) => item.text())).toEqual(['Project A', 'Project B'])
    expect(items[0]?.attributes('aria-current')).toBe('true')
    expect(items[1]?.attributes('href')).toBe(`/projects/${PROJECT_B}/overview`)
    expect(projectMenu().find('a[href="/projects"]').exists()).toBe(false)
    expect(projectMenu().find('hr').exists()).toBe(false)
    expect(wrapper.findAll('aside a[href="/projects"]')).toHaveLength(1)
    expect(projectMenu().element.closest('aside')).toBeNull()
    expect(projectMenu().element.parentElement).toBe(document.body)
    await expectNoAxeViolations(wrapper.get('aside').element)
    await expectNoAxeViolations(projectMenu().element)
  })

  it('recovers from a failed project list while keeping Projects available in the sidebar', async () => {
    const routes: Record<string, RouteResponse> = {
      ...ROUTES,
      '/api/v1/projects': { body: { error: { code: 'x', message: 'x' } }, init: { status: 500 } },
    }
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes(routes),
    )
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('aside .project-switcher-button').exists()).toBe(true))
    await wrapper.get('aside .project-switcher-button').trigger('click')

    await waitFor(() => {
      expect(projectMenu().get('[role="alert"]').text()).toBe(messages.loadError)
    })
    expect(projectMenu().get('button[role="menuitem"]').text()).toBe(
      catalogues[locale].header.retry,
    )
    expect(projectMenu().find('a[href="/projects"]').exists()).toBe(false)
    expect(wrapper.get('aside a[href="/projects"]').text()).toBe(catalogues[locale].nav.projects)
    routes['/api/v1/projects'] = ROUTES['/api/v1/projects']!
    await projectMenu().get('button[role="menuitem"]').trigger('click')
    await flushPromises()
    await wrapper.get('aside .project-switcher-button').trigger('click')
    await waitFor(() => expect(projectMenu().findAll('[role="menuitem"]').length).toBe(2))
    expect(projectMenu().find('[role="alert"]').exists()).toBe(false)
  })

  it('opens by keyboard and restores focus after Escape', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes(ROUTES),
    )
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('aside .project-switcher').exists()).toBe(true))
    const button = wrapper.get<HTMLButtonElement>('aside .project-switcher-button')
    button.element.focus()
    await button.trigger('keydown', { key: 'ArrowDown' })
    await waitFor(() =>
      expect(document.querySelector('.project-switcher-items') !== null).toBe(true),
    )
    const menu = projectMenu()
    await waitFor(() => expect(document.activeElement).toBe(menu.element))
    await menu.trigger('keydown', { key: 'Escape' })
    await waitFor(() =>
      expect(document.querySelector('.project-switcher-items') !== null).toBe(false),
    )
    await waitFor(() => expect(document.activeElement).toBe(button.element))
  })

  it('keeps an accessible current-project name and tooltip in the collapsed rail', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes({
        ...ROUTES,
        '/api/v1/me/preferences': {
          body: { locale, theme: 'system', desktop_sidebar_collapsed: true, revision: 1 },
        },
      }),
    )
    mounted.push(wrapper)
    await waitFor(() =>
      expect(wrapper.get('aside .project-switcher').classes()).toContain(
        'project-switcher--collapsed',
      ),
    )
    const button = wrapper.get<HTMLButtonElement>('aside .project-switcher-button')
    button.element.focus()
    await flushPromises()
    const tooltip = document.getElementById(button.attributes('aria-describedby') ?? '')
    expect(tooltip?.getAttribute('role')).toBe('tooltip')
    expect(tooltip?.textContent).toBe(messages.currentLabel.replace('{project}', 'Project A'))
  })

  it('changes project via its overview and drops switching on global routes', async () => {
    const router = createAppRouter(createMemoryHistory())
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes(ROUTES),
      router,
    )
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('aside .project-switcher').exists()).toBe(true))
    await wrapper.get('aside .project-switcher-button').trigger('click')
    await projectMenu().get(`a[href="/projects/${PROJECT_B}/overview"]`).trigger('click')
    await waitFor(() =>
      expect(wrapper.get('aside .project-switcher-current').text()).toBe('Project B'),
    )
    expect(router.currentRoute.value.params.projectId).toBe(PROJECT_B)
    await wrapper.get('aside .project-switcher-button').trigger('click')
    await wrapper.get('aside a[href="/projects"]').trigger('click')
    await waitFor(() => expect(router.currentRoute.value.name).toBe('projects'))
    expect(wrapper.find('.project-switcher').exists()).toBe(false)
  })

  it('does not retain a stale switcher when the next project is unreadable', async () => {
    const router = createAppRouter(createMemoryHistory())
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes({
        ...ROUTES,
        [`/api/v1/projects/${PROJECT_B}`]: {
          body: { error: { code: 'forbidden', message: 'Forbidden.' } },
          init: { status: 403 },
        },
      }),
      router,
    )
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('aside .project-switcher').exists()).toBe(true))
    await wrapper.get('aside .project-switcher-button').trigger('click')
    expect(projectMenu().element).toBeDefined()
    await router.push(`/projects/${PROJECT_B}/overview`)
    await waitFor(() => expect(wrapper.find('aside .project-switcher').exists()).toBe(false))
    expect(document.querySelector('.project-switcher-items')).toBeNull()
    expect(wrapper.get('aside').text()).not.toContain('Project A')
  })

  it('announces a pending and empty list while keeping Projects available in the sidebar', async () => {
    let resolveList!: (response: Response) => void
    const list = new Promise<Response>((resolve) => {
      resolveList = resolve
    })
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path === '/api/v1/projects') return list
        const route = ROUTES[path]
        return Promise.resolve(
          Response.json(route?.body ?? {}, route?.init ?? { status: route ? 200 : 404 }),
        )
      },
    })
    const wrapper = await mountApplicationAt(`/projects/${PROJECT_A}/overview`, locale, client)
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('aside .project-switcher').exists()).toBe(true))
    await wrapper.get('aside .project-switcher-button').trigger('click')
    expect(projectMenu().get('[role="status"]').text()).toBe(messages.loading)
    expect(projectMenu().findAll('[role="menuitem"]')).toHaveLength(0)
    resolveList(Response.json({ items: [], has_more: false, next_cursor: null }))
    await waitFor(() =>
      expect(projectMenu().get('.project-switcher-note').text()).toBe(messages.empty),
    )
    expect(projectMenu().findAll('[role="menuitem"]')).toHaveLength(0)
    expect(projectMenu().find('a[href="/projects"]').exists()).toBe(false)
    expect(wrapper.get('aside a[href="/projects"]').text()).toBe(catalogues[locale].nav.projects)
  })

  it('keeps a portaled popup inside the viewport near its bottom edge and removes it on unmount', async () => {
    vi.stubGlobal('innerWidth', 1024)
    vi.stubGlobal('innerHeight', 640)
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes(ROUTES),
    )
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('aside .project-switcher-button').exists()).toBe(true))
    const button = wrapper.get<HTMLButtonElement>('aside .project-switcher-button')
    vi.spyOn(button.element, 'getBoundingClientRect').mockReturnValue(new DOMRect(960, 588, 44, 44))
    await button.trigger('click')
    const menu = projectMenu()
    // jsdom has no layout engine: these dimensions exercise placement arithmetic and lifecycle,
    // while actual stacking, text reflow, and clipping remain part of browser verification.
    vi.spyOn(menu.element, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 320, 320))
    Object.defineProperty(menu.element, 'scrollHeight', { value: 320, configurable: true })
    window.dispatchEvent(new Event('resize'))
    await waitFor(() => {
      const height = parseFloat(menu.element.style.maxHeight)
      const top = parseFloat(menu.element.style.top)
      const left = parseFloat(menu.element.style.left)
      expect(height).toBeGreaterThan(0)
      expect(top).toBeGreaterThanOrEqual(8)
      expect(top + Math.min(320, height)).toBeLessThanOrEqual(588)
      expect(left).toBeGreaterThanOrEqual(8)
      expect(left + 320).toBeLessThanOrEqual(1016)
    })
    expect(menu.element.closest('aside')).toBeNull()
    wrapper.unmount()
    mounted.splice(mounted.indexOf(wrapper), 1)
    expect(document.querySelector('.project-switcher-items')).toBeNull()
  })

  it('removes a desktop portal when entering mobile and moves focus to the navigation trigger', async () => {
    const breakpoint = new BreakpointQuery()
    const originalMatchMedia = window.matchMedia
    vi.stubGlobal('matchMedia', (query: string) =>
      query === breakpoint.media ? breakpoint : originalMatchMedia(query),
    )
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes(ROUTES),
    )
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('aside .project-switcher-button').exists()).toBe(true))
    const button = wrapper.get<HTMLButtonElement>('aside .project-switcher-button')
    button.element.focus()
    await button.trigger('keydown', { key: 'ArrowDown' })
    await waitFor(() => expect(document.activeElement).toBe(projectMenu().element))
    breakpoint.setMatches(true)
    await waitFor(() => expect(document.querySelector('.project-switcher-items')).toBeNull())
    expect(wrapper.find('aside .project-switcher-button').exists()).toBe(false)
    await waitFor(() =>
      expect(document.activeElement).toBe(wrapper.get('.app-header-navigation').element),
    )
    breakpoint.setMatches(false)
    await waitFor(() => expect(wrapper.find('aside .project-switcher-button').exists()).toBe(true))
    expect(wrapper.get('aside .project-switcher-button').attributes('aria-expanded')).toBe('false')
    expect(document.querySelector('.project-switcher-items')).toBeNull()
  })

  it('removes the portal while session recovery owns the screen and returns with the menu closed', async () => {
    const recovery = useSessionRecovery()
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes(ROUTES),
    )
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('aside .project-switcher-button').exists()).toBe(true))
    await wrapper.get('aside .project-switcher-button').trigger('click')
    expect(projectMenu().element.parentElement).toBe(document.body)
    recovery.isOpen.value = true
    await waitFor(() => expect(document.querySelector('.project-switcher-items')).toBeNull())
    expect(wrapper.find('aside .project-switcher-button').exists()).toBe(false)
    await waitFor(() => expect(document.querySelector('.session-recovery-panel')).not.toBeNull())
    recovery.resolve()
    await waitFor(() => expect(wrapper.find('aside .project-switcher-button').exists()).toBe(true))
    expect(wrapper.get('aside .project-switcher-button').attributes('aria-expanded')).toBe('false')
    expect(document.querySelector('.project-switcher-items')).toBeNull()
  })

  it('omits redundant label tooltips on hover and focus throughout an expanded sidebar', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_A}/overview`,
      locale,
      apiClientWithRoutes({
        ...ROUTES,
        '/api/v1/me/preferences': {
          body: { locale, theme: 'system', desktop_sidebar_collapsed: false, revision: 1 },
        },
      }),
    )
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('aside .project-switcher-button').exists()).toBe(true))
    for (const selector of [
      'aside a[href="/projects"]',
      'aside [data-preference="locale"] button',
      'aside [data-preference="theme"] button',
      'aside .project-switcher-button',
    ]) {
      const control = wrapper.get<HTMLElement>(selector)
      await control.trigger('mouseenter')
      expect(document.querySelector('[role="tooltip"]')).toBeNull()
      control.element.focus()
      await flushPromises()
      expect(document.querySelector('[role="tooltip"]')).toBeNull()
      expect(control.attributes('aria-describedby')).toBeUndefined()
      control.element.blur()
      await control.trigger('mouseleave')
    }
  })

  it.each([
    { surface: 'navigation', selector: 'aside a[href="/projects"]' },
    { surface: 'language', selector: 'aside [data-preference="locale"] button' },
    { surface: 'theme', selector: 'aside [data-preference="theme"] button' },
    { surface: 'project switching', selector: 'aside .project-switcher-button' },
  ])(
    'shows the $surface label on the forced medium rail and dismisses it on expansion',
    async ({ surface, selector }) => {
      const breakpoint = new BreakpointQuery('(width < 1080px)')
      breakpoint.matches = true
      const originalMatchMedia = window.matchMedia
      vi.stubGlobal('matchMedia', (query: string) =>
        query === breakpoint.media ? breakpoint : originalMatchMedia(query),
      )
      const wrapper = await mountApplicationAt(
        `/projects/${PROJECT_A}/overview`,
        locale,
        apiClientWithRoutes({
          ...ROUTES,
          '/api/v1/me/preferences': {
            body: { locale, theme: 'system', desktop_sidebar_collapsed: false, revision: 1 },
          },
        }),
      )
      mounted.push(wrapper)
      await waitFor(() =>
        expect(wrapper.find('aside .project-switcher-button').exists()).toBe(true),
      )
      expect(wrapper.get('aside').classes()).not.toContain('app-sidebar--desktop-collapsed')
      const control = wrapper.get<HTMLElement>(selector)
      const labels = {
        navigation: catalogues[locale].nav.projects,
        language: catalogues[locale].locale.label,
        theme: catalogues[locale].theme.label,
        'project switching': messages.currentLabel.replace('{project}', 'Project A'),
      }
      await control.trigger('mouseenter')
      await waitFor(() =>
        expect(document.querySelector('[role="tooltip"]')?.textContent).toBe(
          labels[surface as keyof typeof labels],
        ),
      )
      control.element.focus()
      await flushPromises()
      expect(control.attributes('aria-describedby')).toBeDefined()
      breakpoint.setMatches(false)
      await waitFor(() => expect(document.querySelector('[role="tooltip"]')).toBeNull())
      expect(control.attributes('aria-describedby')).toBeUndefined()
      expect(document.activeElement).toBe(control.element)
    },
  )
})
