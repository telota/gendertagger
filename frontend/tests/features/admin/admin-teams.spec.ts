import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes } from '../../helpers/api'
import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const
const ADMIN = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Admin One',
  roles: ['admin'],
}
const OPERATOR = {
  id: 'a0000000-0000-0000-0000-000000000002',
  display_name: 'Operator One',
  roles: ['operator'],
}
const TEAM = {
  id: 'b0000000-0000-0000-0000-000000000001',
  slug: 'edition-alpha',
  display_name: 'Edition Alpha',
  created_at: '2026-09-24T00:00:00Z',
  updated_at: '2026-09-24T00:00:00Z',
}
const TEAM_TWO = {
  id: 'b0000000-0000-0000-0000-000000000002',
  slug: 'edition-beta',
  display_name: 'Edition Beta',
  created_at: '2026-09-24T00:00:00Z',
  updated_at: '2026-09-24T00:00:00Z',
}
const MEMBER = {
  team_id: TEAM.id,
  user_id: 'c0000000-0000-0000-0000-000000000001',
  display_name: 'Member One',
  is_active: true,
  created_at: '2026-09-24T00:00:00Z',
}
const ACTIVE_ACCOUNT = {
  id: 'd0000000-0000-0000-0000-000000000001',
  username: 'active.member',
  display_name: 'Active Member',
  roles: [],
  is_active: true,
  must_change_password: false,
  created_at: '2026-09-24T00:00:00Z',
}
const INACTIVE_ACCOUNT = {
  ...ACTIVE_ACCOUNT,
  id: 'd0000000-0000-0000-0000-000000000002',
  username: 'inactive.member',
  display_name: 'Inactive Member',
  is_active: false,
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  if (init.status === 204) return new Response(null, init)
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function signedInRoutes(
  user: { id: string; display_name: string; roles: string[] },
  teams = [TEAM],
) {
  return {
    '/api/v1/branding': { body: {} },
    '/api/v1/me': { body: user },
    '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    '/api/v1/admin/teams': { body: { items: teams, has_more: false, next_cursor: null } },
    [`/api/v1/admin/teams/${TEAM.id}/members`]: {
      body: { items: [MEMBER], has_more: false, next_cursor: null },
    },
    '/api/v1/admin/users': {
      body: { items: [ACTIVE_ACCOUNT, INACTIVE_ACCOUNT], has_more: false, next_cursor: null },
    },
  }
}

async function selectTeam(wrapper: Awaited<ReturnType<typeof mountApplicationAt>>): Promise<void> {
  const button = wrapper
    .findAll('button')
    .find((candidate) => candidate.text().includes(TEAM.display_name))
  if (!button) throw new Error('The expected team selection was not rendered.')
  await button.trigger('click')
}

afterEach(() => {
  vi.useRealTimers()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('AdminTeamsView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].adminTeams

  it('gates navigation and direct routes to password-current global administrators', async () => {
    const administrator = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes(signedInRoutes(ADMIN)),
    )
    await waitFor(() => {
      expect(administrator.get('aside a[href="/admin/teams"]').text()).toBe(
        catalogues[locale].nav.teams,
      )
    })
    administrator.unmount()

    const operator = await mountApplicationAt(
      '/admin/teams',
      locale,
      apiClientWithRoutes(signedInRoutes(OPERATOR)),
    )
    await flushPromises()
    expect(operator.find('aside a[href="/admin/teams"]').exists()).toBe(false)
    expect(operator.get('[role="alert"]').text()).toBe(messages.forbidden)
  })

  it('debounces server-side team and roster search and resets cursor pagination', async () => {
    vi.useFakeTimers()
    const teamRequests: URL[] = []
    const rosterRequests: URL[] = []
    const client = createApiClient({
      fetch: (request: Request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (url.pathname === '/api/v1/me') return Promise.resolve(jsonResponse(ADMIN))
        if (url.pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (url.pathname === '/api/v1/admin/teams') {
          teamRequests.push(url)
          return Promise.resolve(
            jsonResponse({ items: [TEAM], has_more: false, next_cursor: null }),
          )
        }
        if (url.pathname === `/api/v1/admin/teams/${TEAM.id}/members`) {
          rosterRequests.push(url)
          return Promise.resolve(
            jsonResponse({ items: [MEMBER], has_more: false, next_cursor: null }),
          )
        }
        if (url.pathname === '/api/v1/admin/users') {
          return Promise.resolve(jsonResponse({ items: [], has_more: false, next_cursor: null }))
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/admin/teams', locale, client)
    await vi.advanceTimersByTimeAsync(0)
    await flushPromises()
    expect(teamRequests).toHaveLength(1)

    await wrapper.get('#admin-team-search').setValue('alpha')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    expect(teamRequests.at(-1)?.searchParams.get('query')).toBe('alpha')
    expect(teamRequests.at(-1)?.searchParams.get('cursor')).toBeNull()

    await selectTeam(wrapper)
    await waitFor(() => expect(rosterRequests).toHaveLength(1))
    await wrapper.get('#admin-team-roster-search').setValue('member')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    expect(rosterRequests.at(-1)?.searchParams.get('query')).toBe('member')
    expect(rosterRequests.at(-1)?.searchParams.get('cursor')).toBeNull()
  })

  it('creates and renames a team with only the committed mutable request fields', async () => {
    const requestBodies: unknown[] = []
    const client = createApiClient({
      fetch: async (request: Request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return jsonResponse({})
        if (pathname === '/api/v1/me') return jsonResponse(ADMIN)
        if (pathname === '/api/v1/auth/session') {
          return jsonResponse({ must_change_password: false, keep_signed_in: false })
        }
        if (pathname === '/api/v1/admin/teams' && request.method === 'GET') {
          return jsonResponse({ items: [TEAM], has_more: false, next_cursor: null })
        }
        if (pathname === '/api/v1/admin/teams' && request.method === 'POST') {
          requestBodies.push(JSON.parse(await request.text()) as unknown)
          return jsonResponse(TEAM_TWO, { status: 201 })
        }
        if (pathname === `/api/v1/admin/teams/${TEAM_TWO.id}` && request.method === 'PATCH') {
          requestBodies.push(JSON.parse(await request.text()) as unknown)
          return jsonResponse({ ...TEAM_TWO, display_name: 'Renamed Beta' })
        }
        if (pathname === `/api/v1/admin/teams/${TEAM_TWO.id}/members`) {
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        if (pathname === '/api/v1/admin/users') {
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        return jsonResponse({}, { status: 404 })
      },
    })
    const wrapper = await mountApplicationAt('/admin/teams', locale, client)
    await waitFor(() => expect(wrapper.text()).toContain(TEAM.display_name))

    await wrapper.get('#admin-team-slug').setValue('edition-beta')
    await wrapper.get('#admin-team-display-name').setValue(TEAM_TWO.display_name)
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(wrapper.text()).toContain(TEAM_TWO.display_name))
    await wrapper.get('#admin-team-rename-display-name').setValue('Renamed Beta')
    const forms = wrapper.findAll('form')
    await forms[1]?.trigger('submit')
    await waitFor(() => expect(requestBodies).toHaveLength(2))

    expect(requestBodies).toEqual([
      { slug: 'edition-beta', display_name: TEAM_TWO.display_name },
      { display_name: 'Renamed Beta' },
    ])
    expect(wrapper.text()).toContain(messages.rename.slugImmutable)
  })

  it('disables inactive accounts and accepts the idempotent 200 roster-add response', async () => {
    const memberBodies: unknown[] = []
    const client = createApiClient({
      fetch: async (request: Request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return jsonResponse({})
        if (pathname === '/api/v1/me') return jsonResponse(ADMIN)
        if (pathname === '/api/v1/auth/session') {
          return jsonResponse({ must_change_password: false, keep_signed_in: false })
        }
        if (pathname === '/api/v1/admin/teams') {
          return jsonResponse({ items: [TEAM], has_more: false, next_cursor: null })
        }
        if (pathname === `/api/v1/admin/teams/${TEAM.id}/members` && request.method === 'GET') {
          return jsonResponse({ items: [MEMBER], has_more: false, next_cursor: null })
        }
        if (pathname === `/api/v1/admin/teams/${TEAM.id}/members` && request.method === 'POST') {
          memberBodies.push(JSON.parse(await request.text()) as unknown)
          return jsonResponse({
            ...MEMBER,
            user_id: ACTIVE_ACCOUNT.id,
            display_name: ACTIVE_ACCOUNT.display_name,
          })
        }
        if (pathname === '/api/v1/admin/users') {
          return jsonResponse({
            items: [ACTIVE_ACCOUNT, INACTIVE_ACCOUNT],
            has_more: false,
            next_cursor: null,
          })
        }
        return jsonResponse({}, { status: 404 })
      },
    })
    const wrapper = await mountApplicationAt('/admin/teams', locale, client)
    await waitFor(() => expect(wrapper.text()).toContain(TEAM.display_name))
    await selectTeam(wrapper)
    await waitFor(() => expect(wrapper.text()).toContain(INACTIVE_ACCOUNT.display_name))

    const inactiveButton = wrapper
      .findAll('button')
      .find(
        (button) =>
          button.text() === messages.addMember.add && button.attributes('disabled') !== undefined,
      )
    expect(inactiveButton).toBeDefined()
    const activeButton = wrapper
      .findAll('button')
      .find(
        (button) =>
          button.text() === messages.addMember.add && button.attributes('disabled') === undefined,
      )
    if (!activeButton) throw new Error('The active account add control was not rendered.')
    await activeButton.trigger('click')
    await waitFor(() => expect(memberBodies).toEqual([{ user_id: ACTIVE_ACCOUNT.id }]))
    expect(wrapper.text()).toContain(messages.success.memberConfirmed)
  })

  it('confirms member removal and keeps access intact when replacement is required', async () => {
    const client = createApiClient({
      fetch: (request: Request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(ADMIN))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === '/api/v1/admin/teams') {
          return Promise.resolve(
            jsonResponse({ items: [TEAM], has_more: false, next_cursor: null }),
          )
        }
        if (pathname === `/api/v1/admin/teams/${TEAM.id}/members` && request.method === 'GET') {
          return Promise.resolve(
            jsonResponse({ items: [MEMBER], has_more: false, next_cursor: null }),
          )
        }
        if (pathname === `/api/v1/admin/teams/${TEAM.id}/members/${MEMBER.user_id}`) {
          return Promise.resolve(
            jsonResponse(
              {
                error: { code: 'manager_replacement_required', message: 'Replace manager first.' },
              },
              { status: 409 },
            ),
          )
        }
        if (pathname === '/api/v1/admin/users') {
          return Promise.resolve(jsonResponse({ items: [], has_more: false, next_cursor: null }))
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/admin/teams', locale, client)
    await waitFor(() => expect(wrapper.text()).toContain(TEAM.display_name))
    await selectTeam(wrapper)
    await waitFor(() => expect(wrapper.text()).toContain(MEMBER.display_name))

    const remove = wrapper
      .findAll('button')
      .find((button) => button.text() === messages.roster.remove)
    if (!remove) throw new Error('The member removal control was not rendered.')
    await remove.trigger('click')
    const confirm = wrapper
      .findAll('button')
      .find((button) => button.text() === messages.roster.confirm.submit)
    if (!confirm) throw new Error('The removal confirmation was not rendered.')
    await confirm.trigger('click')
    await waitFor(() =>
      expect(wrapper.text()).toContain(messages.errors.managerReplacementRequired),
    )
    expect(wrapper.text()).toContain(MEMBER.display_name)
  })

  it('confirms deletion and handles the 204 response without inferring emptiness from loaded roster rows', async () => {
    const client = createApiClient({
      fetch: (request: Request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(ADMIN))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === '/api/v1/admin/teams' && request.method === 'GET') {
          return Promise.resolve(
            jsonResponse({ items: [TEAM], has_more: false, next_cursor: null }),
          )
        }
        if (pathname === `/api/v1/admin/teams/${TEAM.id}` && request.method === 'DELETE') {
          return Promise.resolve(jsonResponse(null, { status: 204 }))
        }
        if (pathname === `/api/v1/admin/teams/${TEAM.id}/members`) {
          return Promise.resolve(jsonResponse({ items: [], has_more: false, next_cursor: null }))
        }
        if (pathname === '/api/v1/admin/users') {
          return Promise.resolve(jsonResponse({ items: [], has_more: false, next_cursor: null }))
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt('/admin/teams', locale, client)
    await waitFor(() => expect(wrapper.text()).toContain(TEAM.display_name))
    await selectTeam(wrapper)
    const deleteButton = wrapper
      .findAll('button')
      .find((button) => button.text() === messages.deletion.open)
    if (!deleteButton) throw new Error('The team deletion control was not rendered.')
    await deleteButton.trigger('click')
    expect(wrapper.text()).toContain(messages.deletion.confirm.emptyRequirement)
    const confirm = wrapper
      .findAll('button')
      .find((button) => button.text() === messages.deletion.confirm.submit)
    if (!confirm) throw new Error('The team deletion confirmation was not rendered.')
    await confirm.trigger('click')
    await waitFor(() => expect(wrapper.text()).toContain(messages.success.deleted))
    await expectNoAxeViolations(wrapper.element)
  })
})
