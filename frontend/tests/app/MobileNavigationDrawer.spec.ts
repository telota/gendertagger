import { DOMWrapper, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import { createAppRouter } from '@/app/router'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore } from '@/stores/session'

import { mountApplicationAt } from '../helpers/render'
import { AGG_ID, RUN_ID, newServer, reviewFetch } from '../features/review/fixtures'
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
  options: {
    path?: string
    state?: 'ready' | 'signedOut' | 'passwordChange'
    fetch?: (request: Request) => Promise<Response>
  } = {},
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
      if (options.fetch) return options.fetch(request)
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
        [`/api/v1/projects/${PROJECT}/data-availability`]: {
          project_id: PROJECT,
          has_ready_snapshots: true,
          has_completed_aggregations: false,
        },
        [`/api/v1/projects/${PROJECT}`]: {
          id: PROJECT,
          slug: 'project-a',
          display_name: 'Project A',
          current_user_role: 'viewer',
          working_aggregation_execution_id: null,
          created_at: '2026-01-01T00:00:00Z',
          team: {
            id: 'c0000000-0000-0000-0000-0000000000f1',
            slug: 'editors',
            display_name: 'Editorial Team',
            created_at: '2026-01-01T00:00:00Z',
          },
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
    if (options.state === 'signedOut' && (options.path ?? '/projects') === '/') {
      expect(wrapper.find('.app-header-session').exists()).toBe(false)
      expect(wrapper.get('main form button[type="submit"]').text()).toBe(
        catalogues[locale].login.submit,
      )
    } else expect(wrapper.find('.app-header-session').exists()).toBe(true)
    if (options.state !== 'signedOut' && options.state !== 'passwordChange') {
      expect(preferenceRequests).toContain('GET')
    }
  })
  const trigger = wrapper.find<HTMLButtonElement>('.app-header-navigation')
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

  it('keeps personal settings out of the drawer and closes after project-list navigation', async () => {
    const { wrapper, router, trigger, open } = await application(locale, {
      path: `/projects/${PROJECT}/overview`,
    })
    const drawer = await open()
    expect(drawer.find('a[href="/settings"]').exists()).toBe(false)
    await drawer.get('a[href="/projects"]').trigger('click')
    await waitFor(() => expect(router.currentRoute.value.name).toBe('projects'))
    await waitFor(() => expect(dialog()).toBeNull())
    expect(trigger.attributes('aria-expanded')).toBe('false')
    await waitFor(() => expect(document.activeElement).toBe(wrapper.get('#main-content').element))
  })

  it('opens project switching inside the drawer and returns focus without dismissing navigation', async () => {
    const { open } = await application(locale, { path: `/projects/${PROJECT}/overview` })
    const drawer = await open()
    await waitFor(() => expect(drawer.find('.project-switcher').exists()).toBe(true))
    expect(drawer.get('.project-switcher').classes()).toContain('project-switcher--mobile')
    expect(drawer.get('.project-switcher-current').text()).toBe('Project A')
    const switcher = drawer.get<HTMLButtonElement>('.project-switcher-button')
    switcher.element.focus()
    await switcher.trigger('keydown', { key: 'ArrowDown' })
    await waitFor(() => expect(drawer.find('[role="menu"]').exists()).toBe(true))
    const menu = drawer.get<HTMLElement>('[role="menu"]')
    await waitFor(() => expect(document.activeElement).toBe(menu.element))
    expect(drawer.element.contains(menu.element)).toBe(true)
    await menu.trigger('keydown', { key: 'Escape' })
    await waitFor(() => expect(drawer.find('[role="menu"]').exists()).toBe(false))
    expect(dialog()).not.toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(switcher.element))
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

  it('moves focus to the persistent brand on a signed-in public page', async () => {
    const { wrapper, open, media, preferenceRequests } = await application(locale, {
      path: '/',
    })
    const brand = wrapper.get('aside a.app-sidebar-brand')
    await open()
    await waitFor(() => expect(dialog()?.contains(document.activeElement)).toBe(true))
    vi.stubGlobal('innerWidth', 1080)
    media.get('(width < 720px)')!.setMatches(false)
    await waitFor(() => expect(dialog()).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(brand.element))
    expect(preferenceRequests.every((method) => method === 'GET')).toBe(true)
  })

  it('keeps Members current in the rail and drawer for a management-only manager', async () => {
    const requests: string[] = []
    const responses: Record<string, unknown> = {
      '/api/v1/branding': {},
      '/api/v1/me': USER,
      '/api/v1/auth/session': { must_change_password: false, keep_signed_in: false },
      '/api/v1/me/preferences': {
        locale,
        theme: 'system',
        desktop_sidebar_collapsed: true,
        revision: 2,
      },
      [`/api/v1/projects/${PROJECT}/members`]: {
        manager: { user_id: USER.id, display_name: USER.display_name, project_role: null },
        members: [],
      },
      [`/api/v1/projects/${PROJECT}/eligible-users`]: {
        items: [],
        has_more: false,
        next_cursor: null,
      },
    }
    const { wrapper, open } = await application(locale, {
      path: `/projects/${PROJECT}/members`,
      fetch: (request) => {
        const path = new URL(request.url).pathname
        requests.push(path)
        return Promise.resolve(
          Response.json(responses[path] ?? {}, { status: path in responses ? 200 : 404 }),
        )
      },
    })
    await waitFor(() =>
      expect(wrapper.get('aside [aria-current="page"]').text()).toBe(messages.nav.projectMembers),
    )
    expect(wrapper.get('aside').classes()).toContain('app-sidebar--desktop-collapsed')
    expect(wrapper.findAll('aside nav .nav-item').map((item) => item.text())).toEqual([
      messages.nav.projects,
      messages.nav.projectMembers,
    ])
    expect(wrapper.get('.app-breadcrumbs a').attributes('href')).toBe('/projects')
    expect(wrapper.get('.app-breadcrumbs [aria-current="page"]').text()).toBe(
      messages.projectMembers.title,
    )
    expect(requests.filter((path) => path === `/api/v1/projects/${PROJECT}/members`)).toHaveLength(
      1,
    )

    const drawer = await open()
    await waitFor(() =>
      expect(drawer.get('nav [aria-current="page"]').text()).toBe(messages.nav.projectMembers),
    )
    expect(drawer.get(`a[href="/projects/${PROJECT}/members"]`).classes()).toContain(
      'nav-item--mobile',
    )
    expect(drawer.findAll('nav .nav-item').map((item) => item.text())).toEqual([
      messages.nav.projects,
      messages.nav.projectMembers,
    ])
    expect(drawer.find('.project-switcher').exists()).toBe(false)
    expect(requests).not.toContain(`/api/v1/projects/${PROJECT}`)
    expect(
      requests.some(
        (path) => path.startsWith('/api/v1/runs/') || path.startsWith('/api/v1/aggregations/'),
      ),
    ).toBe(false)
  })

  it('shows the same viewer destinations as the persistent navigation', async () => {
    const { wrapper, open } = await application(locale, { path: `/projects/${PROJECT}/overview` })
    await waitFor(() => expect(wrapper.get('aside').text()).toContain(messages.nav.currentProject))
    const persistentItems = wrapper.findAll('aside nav .nav-item').map((item) => item.text())
    const drawer = await open()
    expect(drawer.findAll('nav .nav-item').map((item) => item.text())).toEqual(persistentItems)
    expect(persistentItems).not.toContain(messages.nav.annotate)
    expect(persistentItems).toContain(messages.nav.data)
    expect(persistentItems).not.toContain(messages.nav.import)
    expect(persistentItems).not.toContain(messages.nav.review)
  })

  it.each(['signedOut', 'passwordChange'] as const)(
    'offers the public header without a drawer or sidebar for %s',
    async (state) => {
      const { wrapper, trigger, preferenceRequests } = await application(locale, {
        path: '/',
        state,
      })
      expect(trigger.exists()).toBe(false)
      expect(wrapper.find('.app-sidebar').exists()).toBe(false)
      expect(dialog()).toBeNull()
      expect(wrapper.get('.app-header-brand').text()).toBe(messages.app.title)
      expect(wrapper.findAll('header [aria-haspopup="listbox"]')).toHaveLength(2)
      expect(preferenceRequests).toEqual([])
    },
  )

  it('removes an open drawer on session loss and restores private navigation closed', async () => {
    const { wrapper, open } = await application(locale, { path: '/' })
    await open()
    const session = useSessionStore()
    session.forgetSession()
    await waitFor(() => expect(dialog()).toBeNull())
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
    expect(wrapper.get('.app-header-brand').text()).toBe(messages.app.title)
    session.user = USER
    await waitFor(() => expect(wrapper.find('aside').exists()).toBe(true))
    expect(wrapper.get('.app-header-navigation').attributes('aria-expanded')).toBe('false')
    expect(dialog()).toBeNull()
  })

  it('protects a real review draft when switching projects from the drawer', async () => {
    const nextProject = 'b0000000-0000-0000-0000-000000000002'
    const target = `/projects/${nextProject}/overview`
    const reviewPath = `/projects/${PROJECT}/runs/${RUN_ID}/aggregations/${AGG_ID}/review`
    const server = newServer()
    const fetchReview = reviewFetch(server)
    const projectB = {
      id: nextProject,
      slug: 'project-b',
      display_name: 'Project B',
      current_user_role: 'viewer',
      working_aggregation_execution_id: null,
      created_at: '2026-01-01T00:00:00Z',
      team: {
        id: 'c0000000-0000-0000-0000-0000000000f1',
        slug: 'editors',
        display_name: 'Editorial Team',
        created_at: '2026-01-01T00:00:00Z',
      },
    }
    const { wrapper, router, open } = await application(locale, {
      path: reviewPath,
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path === '/api/v1/me/preferences')
          return Promise.resolve(
            Response.json({
              locale,
              theme: 'system',
              desktop_sidebar_collapsed: true,
              revision: 1,
            }),
          )
        if (path === '/api/v1/projects')
          return Promise.resolve(
            Response.json({
              items: [projectB],
              next_cursor: null,
              has_more: false,
            }),
          )
        if (path === `/api/v1/projects/${nextProject}`)
          return Promise.resolve(Response.json(projectB))
        return fetchReview(request)
      },
    })
    await waitFor(() => expect(wrapper.find('#decision-comment').exists()).toBe(true))
    await wrapper.get('#decision-correct-female').setValue(true)
    await wrapper.get('#decision-comment').setValue('Evidence remains in this project')
    const drawer = await open()
    await drawer.get('.project-switcher-button').trigger('click')
    await drawer.get(`.project-switcher a[href="${target}"]`).trigger('click')
    await waitFor(() =>
      expect(document.querySelector('.draft-leave-panel')?.contains(document.activeElement)).toBe(
        true,
      ),
    )
    expect(dialog()).not.toBeNull()
    document.querySelector<HTMLButtonElement>('.draft-leave-actions button')!.click()
    await waitFor(() => expect(document.querySelector('.draft-leave-panel')).toBeNull())
    expect(router.currentRoute.value.path).toBe(reviewPath)
    expect((wrapper.get('#decision-comment').element as HTMLTextAreaElement).value).toBe(
      'Evidence remains in this project',
    )
    await waitFor(() =>
      expect(document.activeElement).toBe(drawer.get('.project-switcher-button').element),
    )
    expect(drawer.find('[role="menu"]').exists()).toBe(false)

    await drawer.get('.project-switcher-button').trigger('click')
    await drawer.get(`.project-switcher a[href="${target}"]`).trigger('click')
    await waitFor(() => expect(document.querySelector('.draft-leave-panel')).not.toBeNull())
    document.querySelectorAll<HTMLButtonElement>('.draft-leave-actions button')[1]!.click()
    await waitFor(() => expect(router.currentRoute.value.path).toBe(target))
    await waitFor(() => expect(dialog()).toBeNull())
    expect(document.querySelector('.draft-leave-panel')).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(wrapper.get('#main-content').element))
    expect(server.posts).toHaveLength(0)
  })
})
