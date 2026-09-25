import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient, type ApiClient } from '@/api'
import AppSidebar from '@/app/AppSidebar.vue'
import { createAppI18n, type AppLocale } from '@/app/i18n'
import { createQueryClient } from '@/app/queryClient'
import { createAppRouter } from '@/app/router'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import type { AccessibleProject } from '@/features/projects/useProjects'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore, type CurrentUser } from '@/stores/session'

import { apiClientWithRoutes } from '../helpers/api'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const
const PROJECT_A = 'b0000000-0000-0000-0000-000000000001'
const PROJECT_B = 'b0000000-0000-0000-0000-000000000002'
const RUN = 'c0000000-0000-0000-0000-000000000001'
const AGGREGATION = 'd0000000-0000-0000-0000-000000000001'
const SNAPSHOT = 'e0000000-0000-0000-0000-000000000001'
const USER: CurrentUser = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Sidebar user',
  roles: [],
}
const DEFAULT_PREFERENCES = {
  locale: null,
  theme: 'system',
  desktop_sidebar_collapsed: false,
  revision: 0,
}
const AGGREGATION_PATH = `/projects/${PROJECT_A}/runs/${RUN}/aggregations/${AGGREGATION}`
type ProjectRole = AccessibleProject['current_user_role']
type SessionStore = ReturnType<typeof useSessionStore>
type SessionState = Pick<SessionStore, 'status' | 'user' | 'mustChangePassword'>
type NavKey = keyof typeof en.nav
const VIEWER_ITEMS: NavKey[] = [
  'projects',
  'overview',
  'classification',
  'annotate',
  'evaluations',
  'exports',
]
const ROLE_ITEMS: Record<ProjectRole, NavKey[]> = {
  viewer: VIEWER_ITEMS,
  reviewer: [
    'projects',
    'overview',
    'classification',
    'review',
    'annotate',
    'evaluations',
    'exports',
  ],
  operator: [
    'projects',
    'overview',
    'import',
    'classification',
    'review',
    'annotate',
    'evaluations',
    'exports',
  ],
}

function project(id: string, role: ProjectRole): AccessibleProject {
  return {
    id,
    slug: id === PROJECT_A ? 'project-a' : 'project-b',
    display_name: id === PROJECT_A ? 'Project A' : 'Project B',
    current_user_role: role,
    current_user_can_manage_members: role === 'operator',
    created_by_user_id: USER.id,
    manager_user_id: USER.id,
    team: {
      id: 'f0000000-0000-0000-0000-000000000001',
      slug: 'test-team',
      display_name: 'Test team',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    created_at: '2026-01-01T00:00:00Z',
    working_aggregation_execution_id: null,
  }
}

function clientForRole(role: ProjectRole): ApiClient {
  return apiClientWithRoutes({
    '/api/v1/projects': { body: { items: [], has_more: false, next_cursor: null } },
    [`/api/v1/projects/${PROJECT_A}`]: { body: project(PROJECT_A, role) },
    [`/api/v1/runs/${RUN}`]: { body: { id: RUN, dataset_snapshot_id: SNAPSHOT } },
    '/api/v1/auth/logout': { body: null, init: { status: 204 } },
  })
}

/** Hold one server response so permission loading and project switches can be observed directly. */
function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return {
    promise,
    respond(body: unknown, status = 200) {
      resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { 'content-type': 'application/json' },
        }),
      )
    },
  }
}

const cleanups: (() => void)[] = []

/** Mount navigation surfaces; route screens cannot issue unrelated queries or redirects. */
async function mountSidebar(
  path: string,
  locale: AppLocale,
  client: ApiClient = clientForRole('operator'),
  state: Partial<SessionState> = {},
) {
  const router = createAppRouter(createMemoryHistory())
  const queryClient = createQueryClient()
  const pinia = createPinia()
  let session!: SessionStore
  await router.push(path)
  await router.isReady()
  const wrapper = mount(
    defineComponent({
      setup() {
        session = useSessionStore()
        session.$patch({ status: 'ready', user: { ...USER }, mustChangePassword: false, ...state })
        return () => h(AppSidebar)
      },
    }),
    {
      attachTo: document.body,
      global: {
        plugins: [pinia, createAppI18n(locale), router, [VueQueryPlugin, { queryClient }]],
        provide: { [API_CLIENT_KEY as symbol]: client },
      },
    },
  )
  cleanups.push(() => {
    wrapper.unmount()
    queryClient.clear()
  })
  await flushPromises()
  return { wrapper, router, queryClient, session }
}

function expectItems(wrapper: VueWrapper, locale: AppLocale, keys: NavKey[]) {
  expect(wrapper.findAll('nav .nav-item').map((item) => item.text())).toEqual(
    keys.map((key) => catalogues[locale].nav[key]),
  )
}

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('sidebar visibility in %s', (locale) => {
  const messages = catalogues[locale].nav

  it.each([
    { label: 'idle', state: { status: 'idle' } },
    { label: 'loading', state: { status: 'loading' } },
    { label: 'session error', state: { status: 'error' } },
    { label: 'signed out', state: { user: null } },
    { label: 'password change required', state: { mustChangePassword: true } },
  ] satisfies { label: string; state: Partial<SessionState> }[])(
    'hides private navigation for $label, even with an admin user and project URL',
    async ({ state }) => {
      const { wrapper } = await mountSidebar(AGGREGATION_PATH, locale, clientForRole('operator'), {
        user: { ...USER, roles: ['admin'] },
        ...state,
      })

      expectItems(wrapper, locale, [])
      expect(wrapper.findAll('nav h2')).toHaveLength(0)
      expect(wrapper.get('a.app-sidebar-brand').attributes('href')).toBe('/')
    },
  )

  it('keeps Projects available to a ready signed-in account with no projects', async () => {
    const { wrapper } = await mountSidebar('/projects', locale)

    expectItems(wrapper, locale, ['projects'])
    expect(wrapper.get('nav a').attributes('href')).toBe('/projects')
    expect(wrapper.findAll('nav h2')).toHaveLength(0)
  })

  it.each(['viewer', 'reviewer', 'operator'] as const)(
    'shows exactly the destinations allowed by the effective %s project role',
    async (role) => {
      const { wrapper } = await mountSidebar(AGGREGATION_PATH, locale, clientForRole(role))

      await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS[role]))
      await waitFor(() => expect(wrapper.findAll('nav [aria-disabled="true"]')).toHaveLength(0))
      expect(wrapper.findAll('nav h2').map((heading) => heading.text())).toEqual([
        messages.currentProject,
        messages.evaluationGroup,
      ])
      expect(
        wrapper
          .findAll('nav a')
          .some((item) => item.attributes('href') === `/projects/${PROJECT_A}/runs/${RUN}/exports`),
      ).toBe(true)
    },
  )

  it('does not upgrade a project viewer because their global role is operator', async () => {
    const { wrapper } = await mountSidebar(AGGREGATION_PATH, locale, clientForRole('viewer'), {
      user: { ...USER, roles: ['operator'] },
    })

    await waitFor(() => expectItems(wrapper, locale, VIEWER_ITEMS))
  })

  it('shows administration to an eligible admin and uses their effective project operator role', async () => {
    const { wrapper } = await mountSidebar(AGGREGATION_PATH, locale, clientForRole('operator'), {
      user: { ...USER, roles: ['admin'] },
    })

    await waitFor(() =>
      expectItems(wrapper, locale, [...ROLE_ITEMS.operator, 'administration', 'teams', 'settings']),
    )
    expect(
      wrapper
        .findAll('nav a')
        .filter((item) => item.attributes('href')?.startsWith('/admin/'))
        .map((item) => item.attributes('href')),
    ).toEqual(['/admin/users', '/admin/teams', '/admin/settings'])
  })

  it.each(['viewer', 'reviewer', 'operator'] as const)(
    'disables missing resource targets only for entries allowed to a %s',
    async (role) => {
      const { wrapper } = await mountSidebar(
        `/projects/${PROJECT_A}/overview`,
        locale,
        clientForRole(role),
      )

      await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS[role]))
      const disabledKeys = ROLE_ITEMS[role].filter(
        (key) => !['projects', 'overview', 'import'].includes(key),
      )
      expect(wrapper.findAll('nav [aria-disabled="true"]').map((item) => item.text())).toEqual(
        disabledKeys.map((key) => messages[key]),
      )
      expect(wrapper.findAll('nav a').map((item) => item.text())).toEqual(
        (role === 'operator' ? ['projects', 'overview', 'import'] : ['projects', 'overview']).map(
          (key) => messages[key as NavKey],
        ),
      )
    },
  )

  it('waits for the project response before showing its navigation', async () => {
    const response = deferredResponse()
    const client = createApiClient({
      fetch: (request) =>
        new URL(request.url).pathname === `/api/v1/projects/${PROJECT_A}`
          ? response.promise
          : Promise.resolve(Response.json({}, { status: 404 })),
    })
    const { wrapper } = await mountSidebar(`/projects/${PROJECT_A}/overview`, locale, client)

    expectItems(wrapper, locale, ['projects'])
    expect(wrapper.findAll('nav h2')).toHaveLength(0)

    response.respond(project(PROJECT_A, 'viewer'))
    await waitFor(() => expectItems(wrapper, locale, VIEWER_ITEMS))
  })

  it.each([403, 404])('hides the project group when its request returns %s', async (status) => {
    const client = apiClientWithRoutes({
      [`/api/v1/projects/${PROJECT_A}`]: {
        body: { error: { code: 'resource_not_found', message: 'Project unavailable.' } },
        init: { status },
      },
    })
    const { wrapper, queryClient } = await mountSidebar(
      `/projects/${PROJECT_A}/overview`,
      locale,
      client,
    )

    await waitFor(() =>
      expect(
        queryClient
          .getQueryCache()
          .findAll({ queryKey: ['projects'] })
          .some((query) => query.state.status === 'error'),
      ).toBe(true),
    )
    expectItems(wrapper, locale, ['projects'])
    expect(wrapper.findAll('nav h2')).toHaveLength(0)
  })

  it.each([null, 'unrecognized-role'])(
    'hides project navigation with an invalid role %s',
    async (role) => {
      const client = apiClientWithRoutes({
        [`/api/v1/projects/${PROJECT_A}`]: {
          body: { ...project(PROJECT_A, 'viewer'), current_user_role: role },
        },
      })
      const { wrapper, queryClient } = await mountSidebar(
        `/projects/${PROJECT_A}/overview`,
        locale,
        client,
      )

      await waitFor(() =>
        expect(
          queryClient
            .getQueryCache()
            .findAll({ queryKey: ['projects'] })
            .some((query) => query.state.status === 'success'),
        ).toBe(true),
      )
      expectItems(wrapper, locale, ['projects'])
      expect(wrapper.findAll('nav h2')).toHaveLength(0)
    },
  )

  it('does not reuse an account’s cached project role for a different signed-in account', async () => {
    const response = deferredResponse()
    let projectRequests = 0
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path === '/api/v1/me/preferences') {
          return Promise.resolve(Response.json(DEFAULT_PREFERENCES))
        }
        if (path !== `/api/v1/projects/${PROJECT_A}`) {
          return Promise.resolve(Response.json({}, { status: 404 }))
        }
        projectRequests += 1
        return projectRequests > 1
          ? response.promise
          : Promise.resolve(
              new Response(JSON.stringify(project(PROJECT_A, 'operator')), {
                headers: { 'content-type': 'application/json' },
              }),
            )
      },
    })
    const { wrapper, session } = await mountSidebar(
      `/projects/${PROJECT_A}/overview`,
      locale,
      client,
    )
    await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS.operator))

    session.user = { ...USER, id: 'a0000000-0000-0000-0000-000000000002' }
    await flushPromises()
    expectItems(wrapper, locale, ['projects'])

    response.respond(project(PROJECT_A, 'viewer'))
    await waitFor(() => expectItems(wrapper, locale, VIEWER_ITEMS))
    expect(projectRequests).toBe(2)
  })

  it('removes the previous account’s project list while the new account’s list loads', async () => {
    const response = deferredResponse()
    const messages = catalogues[locale].projectSwitcher
    let projectRequests = 0
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path === '/api/v1/me/preferences')
          return Promise.resolve(Response.json(DEFAULT_PREFERENCES))
        if (path === `/api/v1/projects/${PROJECT_A}`)
          return Promise.resolve(Response.json(project(PROJECT_A, 'viewer')))
        if (path !== '/api/v1/projects') return Promise.resolve(Response.json({}, { status: 404 }))
        projectRequests += 1
        return projectRequests > 1
          ? response.promise
          : Promise.resolve(
              Response.json({
                items: [project(PROJECT_B, 'operator')],
                has_more: false,
                next_cursor: null,
              }),
            )
      },
    })
    const { wrapper, session } = await mountSidebar(
      `/projects/${PROJECT_A}/overview`,
      locale,
      client,
    )
    await waitFor(() => expect(wrapper.find('.project-switcher-button').exists()).toBe(true))
    await wrapper.get('.project-switcher-button').trigger('click')
    const menuNames = () =>
      Array.from(document.querySelectorAll('.project-switcher-items [role="menuitem"]'), (item) =>
        item.textContent?.trim(),
      )
    await waitFor(() => expect(menuNames()).toEqual(['Project B']))

    session.user = { ...USER, id: 'a0000000-0000-0000-0000-000000000002' }
    await flushPromises()
    await waitFor(() => expect(wrapper.find('.project-switcher-button').exists()).toBe(true))
    expect(document.querySelector('.project-switcher-items')).toBeNull()
    await wrapper.get('.project-switcher-button').trigger('click')
    expect(menuNames()).toEqual([])
    expect(
      document.querySelector('.project-switcher-items [role="status"]')?.textContent?.trim(),
    ).toBe(messages.loading)
    expect(document.body.textContent).not.toContain('Project B')

    response.respond({ items: [project(PROJECT_A, 'viewer')], has_more: false, next_cursor: null })
    await waitFor(() => expect(menuNames()).toEqual(['Project A']))
    expect(projectRequests).toBe(2)
  })

  it('hides the project switcher without fetching projects while a password change is required', async () => {
    const requests: string[] = []
    const client = createApiClient({
      fetch: (request) => {
        requests.push(new URL(request.url).pathname)
        return Promise.resolve(new Response(null, { status: 204 }))
      },
    })
    const { wrapper } = await mountSidebar(`/projects/${PROJECT_A}/overview`, locale, client, {
      mustChangePassword: true,
    })

    expect(wrapper.find('button[aria-haspopup="menu"]').exists()).toBe(false)
    expectItems(wrapper, locale, [])
    expect(requests).toEqual([])
  })

  it('drops the old project role during a switch and resolves the new project independently', async () => {
    const response = deferredResponse()
    const client = createApiClient({
      fetch: (request) =>
        new URL(request.url).pathname === `/api/v1/projects/${PROJECT_B}`
          ? response.promise
          : Promise.resolve(
              new Response(JSON.stringify(project(PROJECT_A, 'operator')), {
                headers: { 'content-type': 'application/json' },
              }),
            ),
    })
    const { wrapper, router } = await mountSidebar(
      `/projects/${PROJECT_A}/overview`,
      locale,
      client,
    )
    await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS.operator))

    await router.push(`/projects/${PROJECT_B}/overview`)
    await flushPromises()
    expectItems(wrapper, locale, ['projects'])

    response.respond(project(PROJECT_B, 'viewer'))
    await waitFor(() => expectItems(wrapper, locale, VIEWER_ITEMS))
    expect(wrapper.findAll('nav a').map((item) => item.attributes('href'))).toEqual([
      '/projects',
      `/projects/${PROJECT_B}/overview`,
    ])
  })

  it.each(['logout', 'session error', 'password change required'] as const)(
    'hides cached project and admin navigation after %s',
    async (transition) => {
      const { wrapper, session, queryClient } = await mountSidebar(
        `/projects/${PROJECT_A}/overview`,
        locale,
        clientForRole('operator'),
        { user: { ...USER, roles: ['admin'] } },
      )
      await waitFor(() =>
        expectItems(wrapper, locale, [
          ...ROLE_ITEMS.operator,
          'administration',
          'teams',
          'settings',
        ]),
      )
      const cachedProject = () =>
        queryClient
          .getQueryCache()
          .findAll({ queryKey: ['projects'] })
          .find((query) => query.state.data !== undefined)?.state.data
      expect(cachedProject()).toBeDefined()

      if (transition === 'logout') await session.logout()
      else if (transition === 'session error') session.status = 'error'
      else session.mustChangePassword = true
      await flushPromises()

      expectItems(wrapper, locale, [])
      expect(wrapper.findAll('nav h2')).toHaveLength(0)
      expect(cachedProject()).toBeDefined()
    },
  )
})
