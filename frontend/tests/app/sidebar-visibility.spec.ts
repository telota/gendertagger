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
import {
  projectMembershipQueryKey,
  type ProjectMembershipState,
} from '@/features/projects/useProjectMembership'
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
const AVAILABLE = {
  project_id: PROJECT_A,
  has_ready_snapshots: true,
  has_completed_aggregations: true,
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
const VIEWER_ITEMS: NavKey[] = ['projects', 'overview', 'classification', 'evaluations', 'exports']
const PROJECT_VIEWER_ITEMS = VIEWER_ITEMS.slice(0, -2)
const ROLE_ITEMS: Record<ProjectRole, NavKey[]> = {
  viewer: VIEWER_ITEMS,
  reviewer: ['projects', 'overview', 'classification', 'review', 'game', 'evaluations', 'exports'],
  operator: ['projects', 'overview', 'classification', 'review', 'game', 'evaluations', 'exports'],
}

function project(id: string, role: ProjectRole): AccessibleProject {
  return {
    id,
    slug: id === PROJECT_A ? 'project-a' : 'project-b',
    display_name: id === PROJECT_A ? 'Project A' : 'Project B',
    current_user_role: role,
    current_user_can_manage_members: false,
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
    game_mode_enabled: true,
  }
}

function clientForRole(role: ProjectRole, canManageMembers = false): ApiClient {
  return apiClientWithRoutes({
    '/api/v1/projects': { body: { items: [], has_more: false, next_cursor: null } },
    [`/api/v1/projects/${PROJECT_A}/data-availability`]: { body: AVAILABLE },
    [`/api/v1/projects/${PROJECT_A}`]: {
      body: { ...project(PROJECT_A, role), current_user_can_manage_members: canManageMembers },
    },
    [`/api/v1/runs/${RUN}`]: { body: { id: RUN, dataset_snapshot_id: SNAPSHOT } },
    [`/api/v1/aggregations/${AGGREGATION}`]: {
      body: { id: AGGREGATION, run_id: RUN, status: 'completed' },
    },
    [`/api/v1/snapshots/${SNAPSHOT}`]: {
      body: { id: SNAPSHOT, project_id: PROJECT_A, status: 'ready' },
    },
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

function membership(managerId = USER.id, role: ProjectRole | null = null): ProjectMembershipState {
  return {
    manager: { user_id: managerId, display_name: 'Assigned manager', project_role: role },
    members: [],
  }
}

const cleanups: (() => void)[] = []

/** Mount navigation surfaces; route screens cannot issue unrelated queries or redirects. */
async function mountSidebar(
  path: string,
  locale: AppLocale,
  client: ApiClient = clientForRole('operator'),
  state: Partial<SessionState> = {},
  sidebarProps: { desktopSidebarCollapsed?: boolean } = {},
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
        return () => h(AppSidebar, sidebarProps)
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

  it('shows availability loading separately from an empty project', async () => {
    const availability = deferredResponse()
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path.endsWith('/data-availability')) return availability.promise
        if (path === `/api/v1/projects/${PROJECT_A}`)
          return Promise.resolve(Response.json(project(PROJECT_A, 'reviewer')))
        return Promise.resolve(Response.json({}, { status: 404 }))
      },
    })
    const { wrapper } = await mountSidebar(`/projects/${PROJECT_A}/overview`, locale, client)
    await waitFor(() =>
      expect(wrapper.find('.app-sidebar-availability [role="status"]').text()).toBe(
        catalogues[locale].taskEntry.availabilityLoading,
      ),
    )
    expectItems(wrapper, locale, ['projects', 'overview'])
    availability.respond({
      project_id: PROJECT_A,
      has_ready_snapshots: false,
      has_completed_aggregations: false,
    })
    await waitFor(() => expect(wrapper.find('.app-sidebar-availability').exists()).toBe(false))
    expectItems(wrapper, locale, ['projects', 'overview'])
    expect(wrapper.findAll('nav [aria-disabled="true"]')).toHaveLength(0)
    expect(wrapper.findAll('nav h2')).toHaveLength(1)
  })

  it.each([false, true])(
    'offers accessible retry when availability fails (collapsed: %s)',
    async (collapsed) => {
      let reads = 0
      const client = createApiClient({
        fetch: (request) => {
          const path = new URL(request.url).pathname
          if (path.endsWith('/data-availability')) {
            reads += 1
            return Promise.resolve(
              reads === 1 ? Response.json({}, { status: 500 }) : Response.json(AVAILABLE),
            )
          }
          if (path === `/api/v1/projects/${PROJECT_A}`)
            return Promise.resolve(Response.json(project(PROJECT_A, 'reviewer')))
          return Promise.resolve(Response.json({}, { status: 404 }))
        },
      })
      const { wrapper } = await mountSidebar(
        `/projects/${PROJECT_A}/overview`,
        locale,
        client,
        {},
        { desktopSidebarCollapsed: collapsed },
      )
      await waitFor(() =>
        expect(wrapper.find('.app-sidebar-availability [role="status"]').text()).toBe(
          catalogues[locale].taskEntry.availabilityError,
        ),
      )
      expectItems(wrapper, locale, ['projects', 'overview'])
      const retry = wrapper.get('.app-sidebar-availability-retry')
      expect(retry.attributes('aria-label')).toBe(catalogues[locale].taskEntry.retryAvailability)
      await retry.trigger('click')
      await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS.reviewer.slice(0, -2)))
      expect(reads).toBe(2)
      expect(wrapper.find('.app-sidebar-availability').exists()).toBe(false)
    },
  )

  it('does not reuse availability across accounts or projects', async () => {
    const secondAccount = deferredResponse()
    const secondProject = deferredResponse()
    let availabilityReads = 0
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path === `/api/v1/projects/${PROJECT_A}/data-availability`) {
          availabilityReads += 1
          return availabilityReads === 1
            ? Promise.resolve(Response.json(AVAILABLE))
            : secondAccount.promise
        }
        if (path === `/api/v1/projects/${PROJECT_B}/data-availability`) return secondProject.promise
        if (path === `/api/v1/projects/${PROJECT_A}` || path === `/api/v1/projects/${PROJECT_B}`)
          return Promise.resolve(
            Response.json(project(path.endsWith(PROJECT_A) ? PROJECT_A : PROJECT_B, 'reviewer')),
          )
        return Promise.resolve(Response.json({}, { status: 404 }))
      },
    })
    const { wrapper, router, session } = await mountSidebar(
      `/projects/${PROJECT_A}/overview`,
      locale,
      client,
    )
    await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS.reviewer.slice(0, -2)))
    session.user = { ...USER, id: 'another-account' }
    await waitFor(() =>
      expect(wrapper.find('.app-sidebar-availability [role="status"]').text()).toBe(
        catalogues[locale].taskEntry.availabilityLoading,
      ),
    )
    expectItems(wrapper, locale, ['projects', 'overview'])
    secondAccount.respond({ ...AVAILABLE, has_completed_aggregations: false })
    await waitFor(() =>
      expectItems(wrapper, locale, ['projects', 'overview', 'classification', 'review']),
    )
    await router.push(`/projects/${PROJECT_B}/overview`)
    await waitFor(() =>
      expect(wrapper.find('.app-sidebar-availability [role="status"]').text()).toBe(
        catalogues[locale].taskEntry.availabilityLoading,
      ),
    )
    expectItems(wrapper, locale, ['projects', 'overview'])
    secondProject.respond({
      project_id: PROJECT_B,
      has_ready_snapshots: false,
      has_completed_aggregations: false,
    })
    await waitFor(() => expect(wrapper.find('.app-sidebar-availability').exists()).toBe(false))
    expectItems(wrapper, locale, ['projects', 'overview'])
    expect(wrapper.find(`nav a[href*="${PROJECT_A}"]`).exists()).toBe(false)
  })

  it.each(['viewer', 'reviewer', 'operator'] as const)(
    'shows exactly the destinations allowed by the effective %s project role',
    async (role) => {
      const { wrapper } = await mountSidebar(AGGREGATION_PATH, locale, clientForRole(role))

      await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS[role]))
      await waitFor(() => expect(wrapper.findAll('nav [aria-disabled="true"]')).toHaveLength(0))
      expect(wrapper.findAll('nav h2').map((heading) => heading.text())).toEqual([
        messages.currentProject,
        ...(role === 'viewer' ? [] : [messages.additionalGroup]),
        messages.evaluationGroup,
      ])
      expect(
        wrapper
          .findAll('nav a')
          .some((item) => item.attributes('href') === `/projects/${PROJECT_A}/runs/${RUN}/exports`),
      ).toBe(true)
    },
  )

  it('waits for snapshot ownership before exposing explicit run links', async () => {
    const snapshotResponse = deferredResponse()
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path.endsWith('/data-availability'))
          return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
        if (path === `/api/v1/projects/${PROJECT_A}`)
          return Promise.resolve(Response.json(project(PROJECT_A, 'reviewer')))
        if (path === `/api/v1/aggregations/${AGGREGATION}`)
          return Promise.resolve(
            Response.json({ id: AGGREGATION, run_id: RUN, status: 'completed' }),
          )
        if (path === `/api/v1/runs/${RUN}`)
          return Promise.resolve(Response.json({ id: RUN, dataset_snapshot_id: SNAPSHOT }))
        if (path === `/api/v1/snapshots/${SNAPSHOT}`) return snapshotResponse.promise
        return Promise.resolve(Response.json({}, { status: 404 }))
      },
    })
    const { wrapper, queryClient } = await mountSidebar(AGGREGATION_PATH, locale, client)
    await waitFor(() => expect(queryClient.getQueryData(['runs', RUN])).toMatchObject({ id: RUN }))
    expect(wrapper.find('nav a[href$="/exports"]').exists()).toBe(false)
    snapshotResponse.respond({ id: SNAPSHOT, project_id: PROJECT_A, status: 'ready' })
    await waitFor(() => expect(wrapper.find('nav a[href$="/exports"]').exists()).toBe(true))
    expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/annotation"]`).exists()).toBe(true)
  })

  it.each([
    { mismatch: 'aggregation ID', aggregation: { id: 'another-aggregation' }, runAvailable: true },
    { mismatch: 'aggregation run', aggregation: { run_id: 'another-run' }, runAvailable: true },
    { mismatch: 'run ID', run: { id: 'another-run' }, runAvailable: false },
    { mismatch: 'snapshot ID', snapshot: { id: 'another-snapshot' }, runAvailable: false },
    { mismatch: 'snapshot project', snapshot: { project_id: PROJECT_B }, runAvailable: false },
  ])('does not mix resource identities after a mismatched $mismatch', async (entry) => {
    const client = apiClientWithRoutes({
      [`/api/v1/projects/${PROJECT_A}/data-availability`]: { body: AVAILABLE },
      [`/api/v1/projects/${PROJECT_A}`]: { body: project(PROJECT_A, 'reviewer') },
      [`/api/v1/aggregations/${AGGREGATION}`]: {
        body: { id: AGGREGATION, run_id: RUN, status: 'completed', ...entry.aggregation },
      },
      [`/api/v1/runs/${RUN}`]: {
        body: { id: RUN, dataset_snapshot_id: SNAPSHOT, ...entry.run },
      },
      [`/api/v1/snapshots/${SNAPSHOT}`]: {
        body: { id: SNAPSHOT, project_id: PROJECT_A, status: 'ready', ...entry.snapshot },
      },
    })
    const { wrapper, queryClient } = await mountSidebar(AGGREGATION_PATH, locale, client)
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/overview"]`).exists()).toBe(true)
    expect(wrapper.find(`nav a[href="${AGGREGATION_PATH}/review"]`).exists()).toBe(false)
    expect(wrapper.find('nav a[href$="/people"]').exists()).toBe(false)
    expect(wrapper.find('nav a[href$="/exports"]').exists()).toBe(entry.runAvailable)
    expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/classification"]`).exists()).toBe(true)
  })

  it('keeps the selected snapshot but rejects a run from a different snapshot', async () => {
    const snapshotBase = `/projects/${PROJECT_A}/snapshots/${SNAPSHOT}`
    const { wrapper, queryClient } = await mountSidebar(
      `${snapshotBase}/runs/${RUN}`,
      locale,
      apiClientWithRoutes({
        [`/api/v1/projects/${PROJECT_A}/data-availability`]: { body: AVAILABLE },
        [`/api/v1/projects/${PROJECT_A}`]: { body: project(PROJECT_A, 'reviewer') },
        [`/api/v1/runs/${RUN}`]: { body: { id: RUN, dataset_snapshot_id: 'another-snapshot' } },
        [`/api/v1/snapshots/${SNAPSHOT}`]: {
          body: { id: SNAPSHOT, project_id: PROJECT_A, status: 'ready' },
        },
      }),
    )
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/classification"]`).exists()).toBe(true)
    expect(wrapper.find('nav a[href$="/evaluations"]').exists()).toBe(false)
    expect(wrapper.find('nav a[href$="/exports"]').exists()).toBe(false)
  })

  it.each(['aggregation', 'snapshot'] as const)(
    'removes cached targets after a later %s access denial',
    async (resource) => {
      let denied = false
      const resourcePath =
        resource === 'aggregation'
          ? `/api/v1/aggregations/${AGGREGATION}`
          : `/api/v1/snapshots/${SNAPSHOT}`
      const responses: Record<string, unknown> = {
        [`/api/v1/projects/${PROJECT_A}`]: project(PROJECT_A, 'reviewer'),
        [`/api/v1/aggregations/${AGGREGATION}`]: {
          id: AGGREGATION,
          run_id: RUN,
          status: 'completed',
        },
        [`/api/v1/runs/${RUN}`]: { id: RUN, dataset_snapshot_id: SNAPSHOT },
        [`/api/v1/snapshots/${SNAPSHOT}`]: {
          id: SNAPSHOT,
          project_id: PROJECT_A,
          status: 'ready',
        },
      }
      const client = createApiClient({
        fetch: (request) => {
          const path = new URL(request.url).pathname
          if (path.endsWith('/data-availability'))
            return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
          if (denied && path === resourcePath)
            return Promise.resolve(Response.json({}, { status: 403 }))
          return Promise.resolve(
            Response.json(responses[path] ?? {}, { status: path in responses ? 200 : 404 }),
          )
        },
      })
      const { wrapper, queryClient } = await mountSidebar(AGGREGATION_PATH, locale, client)
      await waitFor(() => expect(wrapper.find('nav a[href$="/exports"]').exists()).toBe(true))
      denied = true
      await queryClient.invalidateQueries({
        queryKey:
          resource === 'aggregation'
            ? ['aggregations', AGGREGATION]
            : ['imported-snapshot', USER.id, PROJECT_A, SNAPSHOT],
        exact: true,
      })
      await waitFor(() => expect(queryClient.isFetching()).toBe(0))
      expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/annotation"]`).exists()).toBe(true)
      expect(wrapper.find('nav a[href$="/exports"]').exists()).toBe(resource === 'aggregation')
      expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/overview"]`).exists()).toBe(true)
    },
  )

  it('resolves snapshot-only classification without fetching runs or the working aggregation', async () => {
    const reads: string[] = []
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path.endsWith('/data-availability'))
          return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
        reads.push(path)
        if (path === `/api/v1/projects/${PROJECT_A}`)
          return Promise.resolve(
            Response.json({
              ...project(PROJECT_A, 'reviewer'),
              working_aggregation_execution_id: AGGREGATION,
            }),
          )
        if (path === `/api/v1/snapshots/${SNAPSHOT}`)
          return Promise.resolve(
            Response.json({ id: SNAPSHOT, project_id: PROJECT_A, status: 'ready' }),
          )
        return Promise.resolve(Response.json({}, { status: 404 }))
      },
    })
    const path = `/projects/${PROJECT_A}/snapshots/${SNAPSHOT}/runs`
    const { wrapper } = await mountSidebar(path, locale, client)
    await waitFor(() =>
      expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/classification"]`).exists()).toBe(
        true,
      ),
    )
    expect(reads.filter((read) => /^\/api\/v1\/(runs|aggregations)\//.test(read))).toEqual([])
    expect(wrapper.find(`nav a[href="${AGGREGATION_PATH}/review"]`).exists()).toBe(false)
  })

  it.each([
    { role: 'viewer', canManage: true },
    { role: 'reviewer', canManage: true },
    { role: 'operator', canManage: false },
    { role: 'operator', canManage: true },
  ] as const)(
    'uses the management capability independently of the $role role ($canManage)',
    async ({ role, canManage }) => {
      const { wrapper } = await mountSidebar(
        AGGREGATION_PATH,
        locale,
        clientForRole(role, canManage),
      )
      await waitFor(() =>
        expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/overview"]`).exists()).toBe(true),
      )
      const entry = wrapper.find(`nav a[href="/projects/${PROJECT_A}/members"]`)
      expect(entry.exists()).toBe(canManage)
      if (canManage) expect(entry.text()).toBe(messages.projectMembers)
    },
  )

  it.each([
    { kind: 'management-only manager', role: null, admin: false },
    { kind: 'readable manager', role: 'viewer', admin: false },
    { kind: 'administrator', role: 'operator', admin: true },
  ] as const)(
    'marks Members for a $kind after membership authorization',
    async ({ role, admin }) => {
      const response = deferredResponse()
      let membershipReads = 0
      let projectReads = 0
      const client = createApiClient({
        fetch: (request) => {
          const path = new URL(request.url).pathname
          if (path.endsWith('/data-availability'))
            return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
          if (path === `/api/v1/projects/${PROJECT_A}/members`) {
            membershipReads += 1
            return response.promise
          }
          if (path === `/api/v1/projects/${PROJECT_A}`) {
            projectReads += 1
            return Promise.resolve(
              Response.json({
                ...project(PROJECT_A, role ?? 'viewer'),
                current_user_can_manage_members: true,
              }),
            )
          }
          if (path === '/api/v1/me/preferences')
            return Promise.resolve(Response.json(DEFAULT_PREFERENCES))
          return Promise.resolve(Response.json({}, { status: 404 }))
        },
      })
      const { wrapper } = await mountSidebar(`/projects/${PROJECT_A}/members`, locale, client, {
        user: { ...USER, roles: admin ? ['admin'] : [] },
      })
      expect(projectReads).toBe(0)
      expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/members"]`).exists()).toBe(false)
      expect(membershipReads).toBe(1)
      response.respond(membership(admin ? 'another-manager' : USER.id, admin ? null : role))
      await waitFor(() =>
        expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/members"]`).exists()).toBe(true),
      )
      if (role !== null) await waitFor(() => expect(projectReads).toBe(1))
      const current = wrapper.findAll('nav [aria-current="page"]')
      expect(current.map((item) => item.text())).toEqual([messages.projectMembers])
      const overview = wrapper.find(`nav a[href="/projects/${PROJECT_A}/overview"]`)
      expect(overview.exists()).toBe(role !== null)
      if (overview.exists()) expect(overview.attributes('aria-current')).toBeUndefined()
      if (role === null) {
        expectItems(wrapper, locale, ['projects', 'projectMembers'])
        expect(wrapper.find('.project-switcher').exists()).toBe(false)
        expect(projectReads).toBe(0)
      }
    },
  )

  it.each([false, true])(
    'removes transferred management without borrowing the new manager’s role (own membership: %s)',
    async (hasOwnRole) => {
      let projectReads = 0
      const client = createApiClient({
        fetch: (request) => {
          const path = new URL(request.url).pathname
          if (path.endsWith('/data-availability'))
            return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
          if (path.endsWith('/members'))
            return Promise.resolve(Response.json(membership(USER.id, 'viewer')))
          if (path === `/api/v1/projects/${PROJECT_A}`) {
            projectReads += 1
            return Promise.resolve(
              Response.json({
                ...project(PROJECT_A, 'viewer'),
                current_user_can_manage_members: true,
              }),
            )
          }
          return Promise.resolve(Response.json(DEFAULT_PREFERENCES))
        },
      })
      const { wrapper, queryClient } = await mountSidebar(
        `/projects/${PROJECT_A}/members`,
        locale,
        client,
      )
      await waitFor(() =>
        expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/overview"]`).exists()).toBe(true),
      )
      expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/members"]`).exists()).toBe(true)
      const transferred = membership('next-manager', 'operator')
      transferred.members = [
        {
          project_id: PROJECT_A,
          user_id: hasOwnRole ? USER.id : 'another-member',
          display_name: 'Project viewer',
          role: 'viewer',
          is_manager: false,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ]
      queryClient.setQueryData(projectMembershipQueryKey(USER.id, PROJECT_A), transferred)
      await waitFor(() =>
        expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/members"]`).exists()).toBe(false),
      )
      expectItems(wrapper, locale, hasOwnRole ? PROJECT_VIEWER_ITEMS : ['projects'])
      expect(wrapper.find('nav [aria-current="page"]').exists()).toBe(false)
      expect(projectReads).toBe(1)
    },
  )

  it('does not revive revoked ordinary access after a later membership denial', async () => {
    let ownRole: ProjectRole | null = 'viewer'
    let denyMembership = false
    let projectReads = 0
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path.endsWith('/data-availability'))
          return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
        if (path === `/api/v1/projects/${PROJECT_A}/members`) {
          return Promise.resolve(
            denyMembership
              ? Response.json(
                  { error: { code: 'resource_not_found', message: 'Management transferred.' } },
                  { status: 404 },
                )
              : Response.json(membership(USER.id, ownRole)),
          )
        }
        if (path === `/api/v1/projects/${PROJECT_A}`) {
          projectReads += 1
          return Promise.resolve(
            Response.json({
              ...project(PROJECT_A, 'viewer'),
              current_user_can_manage_members: true,
            }),
          )
        }
        return Promise.resolve(Response.json(DEFAULT_PREFERENCES))
      },
    })
    const { wrapper, queryClient } = await mountSidebar(
      `/projects/${PROJECT_A}/members`,
      locale,
      client,
    )
    await waitFor(() =>
      expect(wrapper.find(`nav a[href="/projects/${PROJECT_A}/overview"]`).exists()).toBe(true),
    )
    ownRole = null
    await queryClient.invalidateQueries({ queryKey: projectMembershipQueryKey(USER.id, PROJECT_A) })
    await waitFor(() => expectItems(wrapper, locale, ['projects', 'projectMembers']))
    denyMembership = true
    await queryClient.invalidateQueries({ queryKey: projectMembershipQueryKey(USER.id, PROJECT_A) })
    await waitFor(() => expectItems(wrapper, locale, ['projects']))
    expect(wrapper.find('.project-switcher').exists()).toBe(false)
    expect(projectReads).toBe(1)
  })

  it('isolates membership navigation by account and project and removes stale authority on error', async () => {
    const accountResponse = deferredResponse()
    const projectResponse = deferredResponse()
    const nextUser = { ...USER, id: 'next-account' }
    let membershipReads = 0
    let failCurrent = false
    const scientificReads: string[] = []
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path.endsWith('/data-availability'))
          return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
        if (path === `/api/v1/projects/${PROJECT_B}/members`) {
          return failCurrent
            ? Promise.resolve(Response.json({}, { status: 403 }))
            : projectResponse.promise
        }
        if (path === `/api/v1/projects/${PROJECT_A}/members`) {
          membershipReads += 1
          return membershipReads === 1
            ? Promise.resolve(Response.json(membership()))
            : accountResponse.promise
        }
        if (path.startsWith('/api/v1/projects/')) scientificReads.push(path)
        return Promise.resolve(Response.json(DEFAULT_PREFERENCES))
      },
    })
    const { wrapper, session, router, queryClient } = await mountSidebar(
      `/projects/${PROJECT_A}/members`,
      locale,
      client,
    )
    await waitFor(() => expectItems(wrapper, locale, ['projects', 'projectMembers']))
    session.user = nextUser
    await flushPromises()
    expectItems(wrapper, locale, ['projects'])
    accountResponse.respond(membership(nextUser.id))
    await waitFor(() => expectItems(wrapper, locale, ['projects', 'projectMembers']))
    await router.push(`/projects/${PROJECT_B}/members`)
    await flushPromises()
    expectItems(wrapper, locale, ['projects'])
    projectResponse.respond(membership(nextUser.id))
    await waitFor(() =>
      expect(
        wrapper.get(`nav a[href="/projects/${PROJECT_B}/members"]`).attributes('aria-current'),
      ).toBe('page'),
    )
    failCurrent = true
    await queryClient.invalidateQueries({
      queryKey: projectMembershipQueryKey(nextUser.id, PROJECT_B),
    })
    await waitFor(() => expectItems(wrapper, locale, ['projects']))
    expect(scientificReads).toEqual([])
  })

  it('does not upgrade a project viewer because their global role is operator', async () => {
    const { wrapper } = await mountSidebar(AGGREGATION_PATH, locale, clientForRole('viewer'), {
      user: { ...USER, roles: ['operator'] },
    })

    await waitFor(() => expectItems(wrapper, locale, VIEWER_ITEMS))
  })

  it('shows administration to an eligible admin and uses their effective project operator role', async () => {
    const { wrapper } = await mountSidebar(
      AGGREGATION_PATH,
      locale,
      clientForRole('operator', true),
      {
        user: { ...USER, roles: ['admin'] },
      },
    )

    await waitFor(() =>
      expectItems(wrapper, locale, [
        ...ROLE_ITEMS.operator.slice(0, -3),
        'projectMembers',
        'game',
        'evaluations',
        'exports',
        'administration',
        'teams',
        'settings',
      ]),
    )
    expect(
      wrapper
        .findAll('nav a')
        .filter((item) => item.attributes('href')?.startsWith('/admin/'))
        .map((item) => item.attributes('href')),
    ).toEqual(['/admin/users', '/admin/teams', '/admin/settings'])
  })

  it.each(['viewer', 'reviewer', 'operator'] as const)(
    'links independent available tasks for %s while hiding unselected run destinations',
    async (role) => {
      const { wrapper } = await mountSidebar(
        `/projects/${PROJECT_A}/overview`,
        locale,
        clientForRole(role),
      )
      await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS[role].slice(0, -2)))
      expect(wrapper.findAll('nav [aria-disabled="true"]')).toHaveLength(0)
      expect(wrapper.find('nav a[href$="/exports"]').exists()).toBe(false)
      expect(wrapper.find('nav a[href$="/evaluations"]').exists()).toBe(false)
      expect(wrapper.findAll('nav h2').map((heading) => heading.text())).toEqual([
        messages.currentProject,
        ...(role === 'viewer' ? [] : [messages.additionalGroup]),
      ])
    },
  )

  it('waits for the project response before showing its navigation', async () => {
    const response = deferredResponse()
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path.endsWith('/data-availability')) return Promise.resolve(Response.json(AVAILABLE))
        return path === `/api/v1/projects/${PROJECT_A}`
          ? response.promise
          : Promise.resolve(Response.json({}, { status: 404 }))
      },
    })
    const { wrapper } = await mountSidebar(`/projects/${PROJECT_A}/overview`, locale, client)

    expectItems(wrapper, locale, ['projects'])
    expect(wrapper.findAll('nav h2')).toHaveLength(0)

    response.respond(project(PROJECT_A, 'viewer'))
    await waitFor(() => expectItems(wrapper, locale, PROJECT_VIEWER_ITEMS))
  })

  it.each([403, 404])('hides the project group when its request returns %s', async (status) => {
    const client = apiClientWithRoutes({
      [`/api/v1/projects/${PROJECT_A}/data-availability`]: { body: AVAILABLE },
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
        [`/api/v1/projects/${PROJECT_A}/data-availability`]: { body: AVAILABLE },
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
        if (path.endsWith('/data-availability'))
          return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
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
    await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS.operator.slice(0, -2)))

    session.user = { ...USER, id: 'a0000000-0000-0000-0000-000000000002' }
    await flushPromises()
    expectItems(wrapper, locale, ['projects'])

    response.respond(project(PROJECT_A, 'viewer'))
    await waitFor(() => expectItems(wrapper, locale, PROJECT_VIEWER_ITEMS))
    expect(projectRequests).toBe(2)
  })

  it('removes the previous account’s project list while the new account’s list loads', async () => {
    const response = deferredResponse()
    const messages = catalogues[locale].projectSwitcher
    let projectRequests = 0
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path.endsWith('/data-availability'))
          return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
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
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path.endsWith('/data-availability'))
          return Promise.resolve(Response.json({ ...AVAILABLE, project_id: path.split('/')[4] }))
        return path === `/api/v1/projects/${PROJECT_B}`
          ? response.promise
          : Promise.resolve(
              new Response(JSON.stringify(project(PROJECT_A, 'operator')), {
                headers: { 'content-type': 'application/json' },
              }),
            )
      },
    })
    const { wrapper, router } = await mountSidebar(
      `/projects/${PROJECT_A}/overview`,
      locale,
      client,
    )
    await waitFor(() => expectItems(wrapper, locale, ROLE_ITEMS.operator.slice(0, -2)))

    await router.push(`/projects/${PROJECT_B}/overview`)
    await flushPromises()
    expectItems(wrapper, locale, ['projects'])

    response.respond(project(PROJECT_B, 'viewer'))
    await waitFor(() => expectItems(wrapper, locale, PROJECT_VIEWER_ITEMS))
    expect(wrapper.findAll('nav a').map((item) => item.attributes('href'))).toEqual([
      '/projects',
      `/projects/${PROJECT_B}/overview`,
      `/projects/${PROJECT_B}/classification`,
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
          ...ROLE_ITEMS.operator.slice(0, -2),
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
