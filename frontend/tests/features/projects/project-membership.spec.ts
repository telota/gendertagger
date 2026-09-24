import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'

import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const ACTOR = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Manager One',
  roles: ['operator'],
}
const CANDIDATE = {
  id: 'a0000000-0000-0000-0000-000000000002',
  display_name: 'Candidate Two',
}
const MEMBER = {
  project_id: PROJECT_ID,
  user_id: 'a0000000-0000-0000-0000-000000000003',
  display_name: 'Member Three',
  role: 'viewer',
  is_manager: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}
const STATE = {
  manager: { user_id: ACTOR.id, display_name: ACTOR.display_name, project_role: null },
  members: [MEMBER],
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  const responseInit =
    init.status === 204
      ? init
      : { ...init, headers: init.headers ?? { 'content-type': 'application/json' } }
  return new Response(init.status === 204 ? null : JSON.stringify(body), responseInit)
}

afterEach(() => document.body.replaceChildren())

describe('ProjectMembershipView', () => {
  it('loads membership and candidates, then sends role, removal, and transfer writes', async () => {
    const writes: { method: string; pathname: string; body: unknown }[] = []
    const secondCandidate = { ...CANDIDATE, id: 'a0000000-0000-0000-0000-000000000004' }
    const client = createApiClient({
      fetch: async (request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/branding') return jsonResponse({})
        if (url.pathname === '/api/v1/me') return jsonResponse(ACTOR)
        if (url.pathname === '/api/v1/auth/session') {
          return jsonResponse({ must_change_password: false, keep_signed_in: false })
        }
        if (url.pathname === `/api/v1/projects/${PROJECT_ID}/members` && request.method === 'GET') {
          return jsonResponse(STATE)
        }
        if (url.pathname === `/api/v1/projects/${PROJECT_ID}/eligible-users`) {
          return url.searchParams.get('cursor') === 'next'
            ? jsonResponse({ items: [secondCandidate], has_more: false, next_cursor: null })
            : jsonResponse({ items: [CANDIDATE], has_more: true, next_cursor: 'next' })
        }
        if (request.method !== 'GET') {
          writes.push({
            method: request.method,
            pathname: url.pathname,
            body: request.method === 'DELETE' ? null : JSON.parse(await request.clone().text()),
          })
          if (request.method === 'DELETE') return jsonResponse(null, { status: 204 })
          if (url.pathname.endsWith('/manager')) return jsonResponse(STATE)
          return jsonResponse({ ...MEMBER, role: 'reviewer' })
        }
        return jsonResponse({}, { status: 404 })
      },
    })
    const wrapper = await mountApplicationAt(`/projects/${PROJECT_ID}/members`, 'en', client)
    await waitFor(() => expect(wrapper.text()).toContain(MEMBER.display_name))
    expect(wrapper.text()).toContain('No ordinary project role')

    const loadMore = wrapper.findAll('button').find((button) => button.text() === 'Load more')
    await loadMore?.trigger('click')
    await waitFor(() => expect(wrapper.text()).toContain(secondCandidate.display_name))

    const roleSelects = wrapper.findAll('select[aria-label="Project role"]')
    await roleSelects[0]?.setValue('reviewer')
    await waitFor(() => expect(writes).toHaveLength(1))

    const remove = wrapper.findAll('button').find((button) => button.text() === 'Remove role')
    await remove?.trigger('click')
    await waitFor(() => expect(writes).toHaveLength(2))

    await wrapper.get('#transfer').setValue(CANDIDATE.id)
    const transfer = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Transfer management')
    await transfer?.trigger('click')
    await waitFor(() => expect(writes).toHaveLength(3))

    await wrapper.get('select[aria-label="Person"]').setValue(CANDIDATE.id)
    await roleSelects[1]?.setValue('operator')
    const add = wrapper.findAll('button').find((button) => button.text() === 'Add member')
    await add?.trigger('click')
    await waitFor(() => expect(writes).toHaveLength(4))

    expect(writes).toEqual([
      {
        method: 'PUT',
        pathname: `/api/v1/projects/${PROJECT_ID}/members/${MEMBER.user_id}`,
        body: { role: 'reviewer' },
      },
      {
        method: 'DELETE',
        pathname: `/api/v1/projects/${PROJECT_ID}/members/${MEMBER.user_id}`,
        body: null,
      },
      {
        method: 'PUT',
        pathname: `/api/v1/projects/${PROJECT_ID}/manager`,
        body: { manager_user_id: CANDIDATE.id, expected_manager_user_id: ACTOR.id },
      },
      {
        method: 'PUT',
        pathname: `/api/v1/projects/${PROJECT_ID}/members/${CANDIDATE.id}`,
        body: { role: 'operator' },
      },
    ])
  })

  it('renders initial-load and mutation failures distinctly', async () => {
    let failLoad = true
    let mutationAttempts = 0
    const mutationErrors = [
      'project_manager_conflict',
      'team_membership_conflict',
      'resource_not_found',
      'forbidden',
      'validation_error',
      'authentication_required',
      'unknown_error',
    ]
    const client = createApiClient({
      fetch: (request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (url.pathname === '/api/v1/me') return Promise.resolve(jsonResponse(ACTOR))
        if (url.pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (url.pathname === `/api/v1/projects/${PROJECT_ID}/members` && request.method === 'GET') {
          if (failLoad) {
            failLoad = false
            return Promise.resolve(jsonResponse({}, { status: 500 }))
          }
          return Promise.resolve(
            jsonResponse({
              ...STATE,
              manager: { ...STATE.manager, project_role: 'operator' },
            }),
          )
        }
        if (url.pathname === `/api/v1/projects/${PROJECT_ID}/eligible-users`) {
          return Promise.resolve(
            jsonResponse({ items: [CANDIDATE], has_more: false, next_cursor: null }),
          )
        }
        mutationAttempts += 1
        return Promise.resolve(
          jsonResponse(
            {
              error: {
                code: mutationErrors[mutationAttempts - 1],
                message: 'Changed.',
              },
            },
            { status: 409 },
          ),
        )
      },
    })
    const wrapper = await mountApplicationAt(`/projects/${PROJECT_ID}/members`, 'en', client)
    await waitFor(() => expect(wrapper.get('main [role="alert"]').text()).toContain('could not'))

    // Remount to exercise a successful read followed by a rejected membership write.
    wrapper.unmount()
    const ready = await mountApplicationAt(`/projects/${PROJECT_ID}/members`, 'en', client)
    await waitFor(() => expect(ready.text()).toContain(MEMBER.display_name))
    expect(ready.text()).toContain('operator')
    const role = ready.findAll('select[aria-label="Project role"]')[0]
    for (const [index] of mutationErrors.entries()) {
      await role?.setValue(index % 2 === 0 ? 'operator' : 'reviewer')
      await waitFor(() => expect(mutationAttempts).toBe(index + 1))
      expect(ready.get('main [role="alert"]').text()).toContain('not confirmed')
    }
    await flushPromises()
  })
})
