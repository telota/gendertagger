import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import type { CurrentUser } from '@/stores/session'

import { enableAutoUnmount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { apiClientWithRoutes, type RouteResponse } from '../../helpers/api'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
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
const ADMIN: CurrentUser = { ...OPERATOR, id: 'a0000000-0000-0000-0000-000000000004', roles: ['admin'] }

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

async function openCreation(wrapper: VueWrapper): Promise<void> {
  await waitFor(() => expect(wrapper.find('.home-new-project').exists()).toBe(true))
  await wrapper.get('.home-new-project').trigger('click')
  await waitFor(() => expect(wrapper.find('#project-create-name').exists()).toBe(true))
}

describe.each(['de', 'en'] as const)('SignedInHomeView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projects
  const home = catalogues[locale].home.signedIn

  it('shows the empty state and no creation action for a viewer', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes(
        signedInRoutes(VIEWER, { body: { items: [], has_more: false, next_cursor: null } }),
      ),
    )
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe(home.welcomeBack.replace('{name}', VIEWER.display_name))
    expect(wrapper.get('main').text()).toContain(messages.empty)
    expect(wrapper.get('main').text()).toContain(messages.emptyHint)
    expect(wrapper.find('.home-new-project').exists()).toBe(false)
  })

  it('lists a project with role and team, offering "Mitglieder verwalten" only when permitted', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes(
        signedInRoutes(OPERATOR, {
          body: { items: [{ ...PROJECT_A, current_user_role: 'operator' }], has_more: false, next_cursor: null },
        }),
      ),
    )
    await flushPromises()

    const card = wrapper.get('.home-project-row')
    expect(card.text()).toContain('Project A')
    expect(card.text()).toContain('The first project.')
    expect(card.text()).toContain(PROJECT_A.team.display_name)
    expect(card.text()).toContain(messages.role.operator)
    expect(card.get('.home-project-open').attributes('href')).toBe(
      `/projects/${PROJECT_A.id}/overview`,
    )
    expect(card.find('.home-project-manage-members').exists()).toBe(false)
  })

  it('shows "Mitglieder verwalten" only on a card where membership management is permitted', async () => {
    const managed = { ...PROJECT_A, current_user_can_manage_members: true }
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes(
        signedInRoutes(OPERATOR, { body: { items: [managed], has_more: false, next_cursor: null } }),
      ),
    )
    await flushPromises()

    const manage = wrapper.get('.home-project-manage-members')
    expect(manage.text()).toBe(messages.manageMembers)
    expect(manage.attributes('href')).toBe(`/projects/${PROJECT_A.id}/members`)
  })

  it('opens the creation form for an operator and posts the new project', async () => {
    const bodies: unknown[] = []
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
          return jsonResponse({ items: [PROJECT_A.team], has_more: false, next_cursor: null })
        }
        if (url.pathname === '/api/v1/projects' && request.method === 'POST') {
          bodies.push(JSON.parse(await request.clone().text()) as unknown)
          return jsonResponse({ ...PROJECT_A, current_user_role: 'operator' }, { status: 201 })
        }
        return jsonResponse({}, { status: 404 })
      },
    })
    const wrapper = await mountApplicationAt('/', locale, client)
    await openCreation(wrapper)
    await waitFor(() => expect(wrapper.find('#project-create-team').exists()).toBe(true))
    await wrapper.get('#project-create-team').setValue(PROJECT_A.team.id)
    await wrapper.get('#project-create-slug').setValue('new-edition')
    await wrapper.get('#project-create-name').setValue('New edition')
    await wrapper.get('.project-creation form').trigger('submit')
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({
      slug: 'new-edition',
      display_name: 'New edition',
      team_id: PROJECT_A.team.id,
    })
  })

  it('paginates the readable list and shows managed-only projects in their own section', async () => {
    const managedOnly = {
      id: 'b0000000-0000-0000-0000-000000000002',
      slug: 'managed-edition',
      display_name: 'Managed edition',
      team: PROJECT_A.team,
    }
    const routes = {
      ...signedInRoutes(VIEWER, {
        body: { items: [PROJECT_A], has_more: true, next_cursor: 'cursor-1' },
      }),
      '/api/v1/projects/managed': {
        body: { items: [managedOnly], has_more: false, next_cursor: null },
      },
    }
    let calls = 0
    const client = createApiClient({
      fetch: (request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/projects') {
          calls += 1
          if (calls === 2) {
            return Promise.resolve(
              jsonResponse({
                items: [{ ...PROJECT_A, id: 'b0000000-0000-0000-0000-000000000003', display_name: 'Project B' }],
                has_more: false,
                next_cursor: null,
              }),
            )
          }
        }
        const route = routes[url.pathname]
        return Promise.resolve(jsonResponse(route?.body ?? {}, route?.init ?? { status: route ? 200 : 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/', locale, client)
    expect(wrapper.get('.home-project-managed').text()).toContain('Managed edition')
    await wrapper.get('.home-project-load-more').trigger('click')
    await waitFor(() => expect(wrapper.text()).toContain('Project B'))
    expect(wrapper.findAll('.home-project-row').map((row) => row.text())).toContainEqual(
      expect.stringContaining('Project B'),
    )
  })

  it('shows account access and no "view and create projects" link, since the home page already is that page', async () => {
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes(
        signedInRoutes(ADMIN, { body: { items: [], has_more: false, next_cursor: null } }),
      ),
    )
    await flushPromises()

    expect(wrapper.get('.home-workspace').text()).toContain(home.workspace.access.admin)
    expect(wrapper.findAll('.home-workspace-links a').map((link) => link.text())).not.toContain(
      expect.stringContaining('Projekte ansehen'),
    )
    const linkLabels = wrapper.findAll('.home-workspace-links a').map((link) => link.text())
    expect(linkLabels).toContain(home.workspace.users)
  })
})
