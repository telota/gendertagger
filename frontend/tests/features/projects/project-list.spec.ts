import { DOMWrapper, enableAutoUnmount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore, type CurrentUser } from '@/stores/session'

import { apiClientWithRoutes, type RouteResponse } from '../../helpers/api'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function routeResponse(request: Request, routes: Record<string, RouteResponse>): Response {
  const route = routes[new URL(request.url).pathname]
  return jsonResponse(route?.body ?? {}, route?.init ?? { status: route ? 200 : 404 })
}

async function openCreation(wrapper: VueWrapper): Promise<void> {
  await waitFor(() => expect(wrapper.find('.project-list-new-project').exists()).toBe(true))
  await wrapper.get('.project-list-new-project').trigger('click')
  await waitFor(() => expect(wrapper.find('#project-create-name').exists()).toBe(true))
}

async function chooseLeaveAction(label: string): Promise<void> {
  await waitFor(() => expect(document.querySelector('.draft-leave[role="dialog"]')).not.toBeNull())
  const dialog = new DOMWrapper(document.querySelector('.draft-leave[role="dialog"]')!)
  const button = dialog.findAll('button').find((item) => item.text() === label)
  expect(button).toBeDefined()
  await button!.trigger('click')
}

const catalogues = { de, en } as const

const VIEWER: CurrentUser = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Viewer One',
  roles: [],
}
const OPERATOR: CurrentUser = {
  id: 'a0000000-0000-0000-0000-000000000002',
  display_name: 'Operator One',
  roles: ['operator'],
}
const ADMIN: CurrentUser = {
  ...OPERATOR,
  id: 'a0000000-0000-0000-0000-000000000004',
  roles: ['admin'],
}

const PROJECT_A = {
  id: 'b0000000-0000-0000-0000-000000000001',
  slug: 'project-a',
  display_name: 'Project A',
  description: 'The first project.',
  team: {
    id: 'c0000000-0000-0000-0000-000000000001',
    slug: 'editorial-team',
    display_name: 'Editorial team',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  manager_user_id: OPERATOR.id,
  created_by_user_id: OPERATOR.id,
  current_user_role: 'viewer',
  current_user_can_manage_members: false,
  created_at: '2026-01-01T00:00:00Z',
}

function signedInRoutes(
  user: { id: string; display_name: string; roles: string[] },
  projectsBody: RouteResponse,
): Record<string, RouteResponse> {
  return {
    '/api/v1/branding': { body: {} },
    '/api/v1/me': { body: user },
    '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    '/api/v1/projects': projectsBody,
    '/api/v1/projects/managed': { body: { items: [], next_cursor: null, has_more: false } },
    '/api/v1/teams': { body: { items: [], next_cursor: null, has_more: false } },
  }
}

enableAutoUnmount(afterEach)

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('ProjectListView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projects

  it('redirects a signed-out visitor to the login page', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': {
          body: {
            error: { code: 'authentication_required', message: 'Authentication is required.' },
          },
          init: { status: 401 },
        },
      }),
    )

    // /login is lazy; its first import in this test file's process needs more than one
    // macrotask tick to resolve. See tests/helpers/wait.ts.
    await waitFor(() => {
      expect(wrapper.get('main h1').text()).toBe(catalogues[locale].login.title)
    })
  })

  it('shows a load error and a retry when the session itself cannot be checked', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
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

    expect(wrapper.get('main').text()).toContain(messages.sessionLoadError)
  })

  it('shows the empty state when there are no projects', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
      locale,
      apiClientWithRoutes(
        signedInRoutes(VIEWER, { body: { items: [], has_more: false, next_cursor: null } }),
      ),
    )
    await flushPromises()

    expect(wrapper.get('main').text()).toContain(messages.empty)
  })

  it('lists a project with its role, and offers no creation action to a viewer', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
      locale,
      apiClientWithRoutes(
        signedInRoutes(VIEWER, {
          body: { items: [PROJECT_A], has_more: false, next_cursor: null },
        }),
      ),
    )
    await flushPromises()

    expect(wrapper.text()).toContain('Project A')
    expect(wrapper.text()).toContain('The first project.')
    const card = wrapper.get('.project-list-readable .project-card')
    expect(card.text()).toContain(PROJECT_A.team.display_name)
    expect(card.text()).toContain(messages.team)
    expect(card.text()).toContain(messages.yourRole)
    expect(card.text()).toContain(messages.role.viewer)
    expect(card.get('.project-card-link').attributes('href')).toBe(
      `/projects/${PROJECT_A.id}/overview`,
    )
    expect(card.get('.project-card-open-project').text()).toBe(messages.openProject)
    expect(card.get('.project-card-open-project').attributes('aria-label')).toBe(
      messages.openProjectNamed.replace('{project}', PROJECT_A.display_name),
    )
    expect(card.get('.project-card-open-project').attributes('href')).toBe(
      `/projects/${PROJECT_A.id}/overview`,
    )
    expect(card.find('.project-card-manage-members').exists()).toBe(false)
    expect(wrapper.find('.project-list-new-project').exists()).toBe(false)
    expect(wrapper.find('.project-creation').exists()).toBe(false)
  })

  it('opens creation on demand and protects its draft while the form is collapsed', async () => {
    const routes = signedInRoutes(OPERATOR, {
      body: { items: [PROJECT_A], has_more: false, next_cursor: null },
    })
    let teamRequests = 0
    const writes: string[] = []
    const client = createApiClient({
      fetch: (request) => {
        if (new URL(request.url).pathname === '/api/v1/teams') teamRequests += 1
        if (request.method !== 'GET') writes.push(request.method)
        return Promise.resolve(routeResponse(request, routes))
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    const toggle = wrapper.get<HTMLButtonElement>('.project-list-new-project')
    expect(toggle.text()).toBe(messages.newProject)
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.attributes('aria-controls')).toBe('project-creation-panel')
    expect(wrapper.find('.project-creation').exists()).toBe(false)
    expect(teamRequests).toBe(0)
    expect(wrapper.get('.project-list-readable').text()).toContain(PROJECT_A.display_name)

    await openCreation(wrapper)
    await waitFor(() => expect(teamRequests).toBe(1))
    expect(toggle.attributes('aria-expanded')).toBe('true')
    const input = wrapper.get<HTMLInputElement>('#project-create-name')
    await input.setValue('Unsubmitted edition')
    toggle.element.focus()
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('#project-creation-panel').isVisible()).toBe(false)
    expect(input.element.value).toBe('Unsubmitted edition')
    expect(document.activeElement).toBe(toggle.element)

    // Reauthentication temporarily gates private navigation but must not discard this account's draft.
    const session = useSessionStore()
    session.isAuthenticating = true
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('#project-create-name').element).toBe(input.element)
    expect(input.element.value).toBe('Unsubmitted edition')
    session.isAuthenticating = false
    await flushPromises()
    expect(wrapper.get('#project-creation-panel').isVisible()).toBe(false)
    expect(input.element.value).toBe('Unsubmitted edition')

    const navigation = wrapper.vm.$router.push('/')
    await chooseLeaveAction(catalogues[locale].draftNavigation.stay)
    await navigation
    expect(wrapper.vm.$router.currentRoute.value.path).toBe('/projects')
    expect(wrapper.get('#project-creation-panel').isVisible()).toBe(false)
    await toggle.trigger('click')
    expect(toggle.text()).toBe(messages.hideCreation)
    expect(wrapper.get('#project-creation-panel').isVisible()).toBe(true)
    expect(wrapper.get<HTMLInputElement>('#project-create-name').element).toBe(input.element)
    expect(input.element.value).toBe('Unsubmitted edition')
    expect(teamRequests).toBe(1)

    await toggle.trigger('click')
    const confirmedNavigation = wrapper.vm.$router.push('/')
    await chooseLeaveAction(catalogues[locale].draftNavigation.discard)
    await confirmedNavigation
    expect(wrapper.vm.$router.currentRoute.value.path).toBe('/')
    expect(wrapper.find('.project-creation').exists()).toBe(false)
    expect(writes).toEqual([])
  })

  it('resets the creation surface when the principal changes or loses access', async () => {
    const wrapper = await mountApplicationAt(
      '/projects',
      locale,
      apiClientWithRoutes(
        signedInRoutes(OPERATOR, { body: { items: [], has_more: false, next_cursor: null } }),
      ),
    )
    await openCreation(wrapper)
    await wrapper.get('#project-create-name').setValue('Previous account draft')
    useSessionStore().user = ADMIN
    await flushPromises()
    expect(wrapper.get('.project-list-new-project').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.project-creation').exists()).toBe(false)
    await openCreation(wrapper)
    expect(wrapper.get<HTMLInputElement>('#project-create-name').element.value).toBe('')
    useSessionStore().user = { ...ADMIN, roles: [] }
    await flushPromises()
    expect(wrapper.find('.project-list-new-project').exists()).toBe(false)
    expect(wrapper.find('.project-creation').exists()).toBe(false)
  })

  it('shows a load error and retries when asked to', async () => {
    let calls = 0
    const client = createApiClient({
      fetch: (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(VIEWER))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === '/api/v1/projects') {
          calls += 1
          if (calls === 1) {
            return Promise.resolve(
              jsonResponse(
                { error: { code: 'internal_error', message: 'Something went wrong.' } },
                { status: 500 },
              ),
            )
          }
          return Promise.resolve(
            jsonResponse({ items: [PROJECT_A], has_more: false, next_cursor: null }),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    await flushPromises()
    expect(wrapper.get('main').text()).toContain(messages.loadError)

    await wrapper.get('.project-list-retry').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Project A')
  })

  it('retains readable projects during next-page loading and failure, then retries the same cursor', async () => {
    const nextPage = deferredResponse()
    const cursors: (string | null)[] = []
    const nextProject = {
      ...PROJECT_A,
      id: 'b0000000-0000-0000-0000-000000000002',
      display_name: 'Project B',
      current_user_can_manage_members: true,
    }
    const routes = {
      ...signedInRoutes(VIEWER, {
        body: { items: [PROJECT_A], has_more: true, next_cursor: 'cursor-1' },
      }),
      '/api/v1/projects/managed': {
        body: {
          items: [
            {
              id: nextProject.id,
              slug: nextProject.slug,
              display_name: nextProject.display_name,
              team: nextProject.team,
            },
          ],
          has_more: false,
          next_cursor: null,
        },
      },
    }
    const client = createApiClient({
      fetch: (request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/projects') {
          cursors.push(url.searchParams.get('cursor'))
          if (cursors.length === 2) return nextPage.promise
          if (cursors.length === 3)
            return Promise.resolve(
              jsonResponse({
                items: [nextProject],
                has_more: false,
                next_cursor: null,
              }),
            )
        }
        return Promise.resolve(routeResponse(request, routes))
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    const section = wrapper.get('.project-list-readable')
    const loadMore = wrapper.get<HTMLButtonElement>('.project-list-load-more')
    expect(section.text()).toContain('Project A')
    expect(wrapper.get('.project-list-managed').text()).toContain('Project B')
    await loadMore.trigger('click')
    await waitFor(() => expect(cursors).toHaveLength(2))
    expect(loadMore.element.disabled).toBe(true)
    expect(section.get('[role="status"]').text()).toBe(messages.loadingMore)
    expect(section.text()).toContain('Project A')
    await loadMore.trigger('click')
    expect(cursors).toHaveLength(2)

    nextPage.resolve(
      jsonResponse(
        { error: { code: 'internal_error', message: 'Next page failed.' } },
        { status: 500 },
      ),
    )
    await waitFor(() => expect(section.get('[role="alert"]').text()).toBe(messages.loadMoreError))
    expect(section.get('.project-card-link').text()).toBe('Project A')
    expect(wrapper.find('.project-list-retry').exists()).toBe(false)
    expect(loadMore.element.disabled).toBe(false)
    await loadMore.trigger('click')
    await waitFor(() => expect(section.findAll('.project-card')).toHaveLength(2))
    expect(section.findAll('.project-card-link').map((item) => item.text())).toEqual([
      'Project A',
      'Project B',
    ])
    expect(section.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.project-list-load-more').exists()).toBe(false)
    expect(wrapper.find('.project-list-managed').exists()).toBe(false)
    expect(section.get('.project-card-manage-members').attributes('href')).toBe(
      `/projects/${nextProject.id}/members`,
    )
    expect(cursors).toEqual([null, 'cursor-1', 'cursor-1'])
  })

  it('puts permitted management actions on readable cards and deduplicates managed summaries', async () => {
    const managedOnly = {
      id: 'b0000000-0000-0000-0000-000000000002',
      slug: 'managed-edition',
      display_name: 'Managed edition',
      team: PROJECT_A.team,
    }
    const requests: string[] = []
    const routes = {
      ...signedInRoutes(VIEWER, {
        body: {
          items: [{ ...PROJECT_A, current_user_can_manage_members: true }],
          has_more: false,
          next_cursor: null,
        },
      }),
      '/api/v1/projects/managed': {
        body: {
          items: [
            {
              id: PROJECT_A.id,
              slug: PROJECT_A.slug,
              display_name: PROJECT_A.display_name,
              team: PROJECT_A.team,
            },
            managedOnly,
          ],
          has_more: false,
          next_cursor: null,
        },
      },
    }
    const client = createApiClient({
      fetch: (request) => {
        requests.push(new URL(request.url).pathname)
        return Promise.resolve(routeResponse(request, routes))
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    const readable = wrapper.get('.project-list-readable')
    const managed = wrapper.get('.project-list-managed')
    expect(readable.get('.project-card-open-project').attributes('href')).toBe(
      `/projects/${PROJECT_A.id}/overview`,
    )
    const manage = readable.get('.project-card-manage-members')
    expect(manage.text()).toBe(messages.manageMembers)
    expect(manage.attributes('aria-label')).toBe(
      messages.manageMembersNamed.replace('{project}', PROJECT_A.display_name),
    )
    expect(manage.attributes('href')).toBe(`/projects/${PROJECT_A.id}/members`)
    expect(
      readable.element.compareDocumentPosition(managed.element) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).not.toBe(0)
    expect(managed.findAll('.project-card')).toHaveLength(1)
    expect(managed.text()).toContain(managedOnly.display_name)
    expect(managed.text()).not.toContain(PROJECT_A.display_name)
    expect(managed.text()).toContain(PROJECT_A.team.display_name)
    expect(managed.find('.project-card-open-project').exists()).toBe(false)
    expect(managed.findAll('a').map((link) => link.attributes('href'))).toEqual([
      `/projects/${managedOnly.id}/members`,
    ])
    expect(requests.some((path) => path.startsWith(`/api/v1/projects/${managedOnly.id}`))).toBe(
      false,
    )
  })

  it('loads and retries managed discovery independently without hiding readable projects', async () => {
    const pending = deferredResponse()
    let managedRequests = 0
    const routes = signedInRoutes(VIEWER, {
      body: { items: [PROJECT_A], has_more: false, next_cursor: null },
    })
    const client = createApiClient({
      fetch: (request) => {
        if (new URL(request.url).pathname === '/api/v1/projects/managed') {
          managedRequests += 1
          if (managedRequests === 1) return pending.promise
          return Promise.resolve(
            jsonResponse({
              items: [
                {
                  id: 'managed-b',
                  slug: 'managed-b',
                  display_name: 'Managed project',
                  team: PROJECT_A.team,
                },
              ],
              has_more: false,
              next_cursor: null,
            }),
          )
        }
        return Promise.resolve(routeResponse(request, routes))
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    const managed = wrapper.get('.project-list-managed')
    expect(managed.get('[role="status"]').text()).toBe(messages.managedLoading)
    expect(wrapper.get('.project-list-readable .project-card-link').text()).toBe('Project A')
    pending.resolve(
      jsonResponse({ error: { code: 'internal_error', message: 'Unavailable.' } }, { status: 500 }),
    )
    await waitFor(() =>
      expect(managed.get('[role="alert"]').text()).toBe(messages.managedLoadError),
    )
    expect(wrapper.find('.project-list-retry').exists()).toBe(false)
    expect(wrapper.get('.project-list-readable .project-card-link').text()).toBe('Project A')
    await managed.get('.project-list-managed-retry').trigger('click')
    await waitFor(() => expect(managed.text()).toContain('Managed project'))
    expect(managed.find('[role="alert"]').exists()).toBe(false)
    expect(managedRequests).toBe(2)
  })

  it('keeps managed pagination available when loaded summaries are already readable and retries failures', async () => {
    const nextPage = deferredResponse()
    const cursors: (string | null)[] = []
    const duplicate = {
      id: PROJECT_A.id,
      slug: PROJECT_A.slug,
      display_name: PROJECT_A.display_name,
      team: PROJECT_A.team,
    }
    const routes = {
      ...signedInRoutes(VIEWER, {
        body: { items: [PROJECT_A], has_more: false, next_cursor: null },
      }),
      '/api/v1/projects/managed': {
        body: { items: [duplicate], has_more: true, next_cursor: 'managed-next' },
      },
    }
    const client = createApiClient({
      fetch: (request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/projects/managed') {
          cursors.push(url.searchParams.get('cursor'))
          if (cursors.length === 2) return nextPage.promise
          if (cursors.length === 3)
            return Promise.resolve(
              jsonResponse({
                items: [{ ...duplicate, id: 'managed-c', display_name: 'Next managed project' }],
                has_more: false,
                next_cursor: null,
              }),
            )
        }
        return Promise.resolve(routeResponse(request, routes))
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    const managed = wrapper.get('.project-list-managed')
    expect(managed.findAll('.project-card')).toHaveLength(0)
    const loadMore = managed.get<HTMLButtonElement>('.project-list-managed-load-more')
    await loadMore.trigger('click')
    await waitFor(() => expect(cursors).toHaveLength(2))
    expect(loadMore.element.disabled).toBe(true)
    await loadMore.trigger('click')
    expect(cursors).toHaveLength(2)
    nextPage.resolve(
      jsonResponse({ error: { code: 'internal_error', message: 'Unavailable.' } }, { status: 500 }),
    )
    await waitFor(() =>
      expect(managed.get('[role="alert"]').text()).toBe(messages.managedLoadMoreError),
    )
    expect(wrapper.get('.project-list-readable .project-card-link').text()).toBe('Project A')
    expect(loadMore.element.disabled).toBe(false)
    await loadMore.trigger('click')
    await waitFor(() => expect(managed.findAll('.project-card')).toHaveLength(1))
    expect(managed.text()).toContain('Next managed project')
    expect(managed.find('[role="alert"]').exists()).toBe(false)
    expect(managed.find('.project-list-managed-load-more').exists()).toBe(false)
    expect(cursors).toEqual([null, 'managed-next', 'managed-next'])
  })

  it('creates a team-owned project with an administrator-selected manager', async () => {
    const bodies: unknown[] = []
    let createCalls = 0
    let managerPageRequests = 0
    const rejectedCodes = [
      'validation_error',
      'forbidden',
      'resource_not_found',
      'authentication_required',
      'password_change_required',
      'unknown_error',
    ]
    const team = PROJECT_A.team
    const manager = {
      team_id: team.id,
      user_id: OPERATOR.id,
      display_name: OPERATOR.display_name,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    }
    const client = createApiClient({
      fetch: async (request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/branding') return jsonResponse({})
        if (url.pathname === '/api/v1/me') return jsonResponse(ADMIN)
        if (url.pathname === '/api/v1/auth/session') {
          return jsonResponse({ must_change_password: false, keep_signed_in: false })
        }
        if (url.pathname === '/api/v1/projects' && request.method === 'GET') {
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        if (url.pathname === '/api/v1/projects/managed') {
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        if (url.pathname === '/api/v1/teams') {
          return jsonResponse({ items: [team], has_more: false, next_cursor: null })
        }
        if (url.pathname === `/api/v1/admin/teams/${team.id}/members`) {
          managerPageRequests += 1
          return url.searchParams.get('cursor') === 'manager-next'
            ? jsonResponse({
                items: [{ ...manager, user_id: ADMIN.id, is_active: false }],
                has_more: false,
                next_cursor: null,
              })
            : jsonResponse({ items: [manager], has_more: true, next_cursor: 'manager-next' })
        }
        if (url.pathname === '/api/v1/projects' && request.method === 'POST') {
          createCalls += 1
          bodies.push(JSON.parse(await request.clone().text()) as unknown)
          if (createCalls <= rejectedCodes.length) {
            return jsonResponse(
              { error: { code: rejectedCodes[createCalls - 1], message: 'Try again.' } },
              { status: 422 },
            )
          }
          return jsonResponse({ ...PROJECT_A, current_user_role: 'operator' }, { status: 201 })
        }
        if (url.pathname === `/api/v1/projects/${PROJECT_A.id}`) return jsonResponse(PROJECT_A)
        return jsonResponse({}, { status: 404 })
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    await openCreation(wrapper)
    await waitFor(() => expect(wrapper.find('#project-create-team').exists()).toBe(true))
    await wrapper.get('#project-create-team').setValue(team.id)
    await waitFor(() => expect(wrapper.text()).toContain(OPERATOR.display_name))
    const managerLoadMore = wrapper
      .findAll('.project-creation button')
      .find((button) => button.text() === messages.creation.managersLoadMore)
    expect(managerLoadMore).toBeDefined()
    await managerLoadMore!.trigger('click')
    await waitFor(() => expect(managerPageRequests).toBe(2))
    expect(wrapper.find(`#project-create-manager option[value="${ADMIN.id}"]`).exists()).toBe(false)
    await wrapper.get('#project-create-slug').setValue('new-edition')
    await wrapper.get('#project-create-name').setValue('New edition')
    await wrapper.get('#project-create-description').setValue('Project description')
    await wrapper.get('#project-create-manager').setValue(OPERATOR.id)

    for (const [index] of rejectedCodes.entries()) {
      await wrapper.get('.project-creation form').trigger('submit')
      await waitFor(() => expect(createCalls).toBe(index + 1))
      expect(wrapper.find('.project-creation [role="alert"]').exists()).toBe(true)
    }
    await wrapper.get('.project-creation form').trigger('submit')
    await waitFor(() => expect(createCalls).toBe(rejectedCodes.length + 1))

    expect(bodies).toHaveLength(rejectedCodes.length + 1)
    expect(bodies.every((body) => JSON.stringify(body) === JSON.stringify(bodies[0]))).toBe(true)
    expect(bodies[0]).toEqual({
      slug: 'new-edition',
      display_name: 'New edition',
      description: 'Project description',
      team_id: team.id,
      initial_manager_user_id: OPERATOR.id,
    })
  })

  it('preserves a project name edited while creation is pending when navigation is cancelled', async () => {
    let finish!: (response: Response) => void
    const response = new Promise<Response>((resolve) => {
      finish = resolve
    })
    let posted = false
    const client = createApiClient({
      fetch: async (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/projects' && request.method === 'POST') {
          posted = true
          return response
        }
        if (pathname === '/api/v1/branding') return jsonResponse({})
        if (pathname === '/api/v1/me') return jsonResponse(OPERATOR)
        if (pathname === '/api/v1/auth/session')
          return jsonResponse({ must_change_password: false, keep_signed_in: false })
        if (pathname === '/api/v1/teams')
          return jsonResponse({ items: [PROJECT_A.team], has_more: false, next_cursor: null })
        if (pathname === '/api/v1/projects' || pathname === '/api/v1/projects/managed')
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        return jsonResponse({}, { status: 404 })
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    try {
      await openCreation(wrapper)
      await waitFor(() => expect(wrapper.find('#project-create-team').exists()).toBe(true))
      await wrapper.get('#project-create-team').setValue(PROJECT_A.team.id)
      await wrapper.get('#project-create-slug').setValue('edition')
      await wrapper.get('#project-create-name').setValue('Submitted name')
      await wrapper.get('.project-creation form').trigger('submit')
      await waitFor(() => expect(posted).toBe(true))
      await wrapper.get('#project-create-name').setValue('Next draft name')
      finish(jsonResponse({ ...PROJECT_A, current_user_role: 'operator' }, { status: 201 }))
      await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
      const stay = Array.from(
        document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'),
      ).find((button) => button.textContent?.trim() === catalogues[locale].draftNavigation.stay)
      expect(stay).toBeDefined()
      stay?.click()
      await flushPromises()
      expect(wrapper.vm.$router.currentRoute.value.path).toBe('/projects')
      expect(wrapper.get<HTMLInputElement>('#project-create-name').element.value).toBe(
        'Next draft name',
      )
    } finally {
      wrapper.unmount()
    }
  })

  it('lets an operator create in a direct team without optional fields or manager discovery', async () => {
    let body: unknown
    const team = PROJECT_A.team
    const client = createApiClient({
      fetch: async (request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/branding') return jsonResponse({})
        if (url.pathname === '/api/v1/me') return jsonResponse(OPERATOR)
        if (url.pathname === '/api/v1/auth/session') {
          return jsonResponse({ must_change_password: false, keep_signed_in: false })
        }
        if (url.pathname === '/api/v1/projects' && request.method === 'GET') {
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        if (url.pathname === '/api/v1/projects/managed') {
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        if (url.pathname === '/api/v1/teams') {
          return jsonResponse({ items: [team], has_more: false, next_cursor: null })
        }
        if (url.pathname === '/api/v1/projects' && request.method === 'POST') {
          body = JSON.parse(await request.clone().text()) as unknown
          return jsonResponse({ ...PROJECT_A, current_user_role: 'operator' }, { status: 201 })
        }
        if (url.pathname === `/api/v1/projects/${PROJECT_A.id}`) return jsonResponse(PROJECT_A)
        return jsonResponse({}, { status: 404 })
      },
    })
    const wrapper = await mountApplicationAt('/projects', locale, client)
    await openCreation(wrapper)
    await waitFor(() => expect(wrapper.find('#project-create-team').exists()).toBe(true))
    expect(wrapper.find('#project-create-manager').exists()).toBe(false)
    await wrapper.get('.project-creation form').trigger('submit')
    expect(body).toBeUndefined()
    await wrapper.get('#project-create-team').setValue(team.id)
    await wrapper.get('#project-create-slug').setValue('operator-edition')
    await wrapper.get('#project-create-name').setValue('Operator edition')
    await wrapper.get('.project-creation form').trigger('submit')
    await waitFor(() => expect(body).toBeDefined())
    expect(body).toEqual({
      slug: 'operator-edition',
      display_name: 'Operator edition',
      team_id: team.id,
    })
  })
})
