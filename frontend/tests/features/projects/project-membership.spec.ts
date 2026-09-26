import { DOMWrapper, enableAutoUnmount, flushPromises } from '@vue/test-utils'
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

enableAutoUnmount(afterEach)

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

    expect(
      wrapper
        .get('.project-members-add-actions')
        .findAll('button')
        .map((button) => button.text()),
    ).toEqual(['Load more', 'Add member'])
    const loadMore = wrapper.findAll('button').find((button) => button.text() === 'Load more')
    await loadMore?.trigger('click')
    await waitFor(() => expect(wrapper.text()).toContain(secondCandidate.display_name))

    await wrapper.get('tbody select[aria-label="Project role"]').setValue('reviewer')
    await waitFor(() => expect(writes).toHaveLength(1))

    const remove = wrapper.findAll('button').find((button) => button.text() === 'Remove role')
    await remove?.trigger('click')
    await waitFor(() =>
      expect(new DOMWrapper(document.body).find('[role="dialog"]').exists()).toBe(true),
    )
    expect(writes).toHaveLength(1)
    const confirmation = new DOMWrapper(document.body)
      .get('[role="dialog"]')
      .findAll('button')
      .find((button) => button.text() === 'Remove role')
    expect(confirmation).toBeDefined()
    await confirmation?.trigger('click')
    await waitFor(() => expect(writes).toHaveLength(2))

    await wrapper.get('#transfer').setValue(CANDIDATE.id)
    const transfer = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Transfer management')
    await transfer?.trigger('click')
    await waitFor(() => expect(writes).toHaveLength(3))

    await wrapper.get('button[aria-controls="project-member-add-panel"]').trigger('click')
    await wrapper.get('#project-member-candidate').setValue(CANDIDATE.id)
    await wrapper.get('#project-member-role').setValue('operator')
    const add = wrapper.get('.project-members-add-actions button')
    await add.trigger('click')
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

  it.each([
    { membershipStatus: 404, first: 'membership', projectStatus: 200 },
    { membershipStatus: 404, first: 'project', projectStatus: 200 },
    { membershipStatus: 403, first: 'membership', projectStatus: 200 },
    { membershipStatus: 403, first: 'project', projectStatus: 200 },
    { membershipStatus: 404, first: 'membership', projectStatus: 404 },
  ])(
    'rechecks ordinary access after transfer ($membershipStatus, $first first, project $projectStatus)',
    async ({ membershipStatus, first, projectStatus }) => {
      let transferred = false
      let membershipReads = 0
      let projectReads = 0
      let finishMembership!: (response: Response) => void
      let finishProject!: (response: Response) => void
      const membershipResponse = new Promise<Response>((resolve) => {
        finishMembership = resolve
      })
      const projectResponse = new Promise<Response>((resolve) => {
        finishProject = resolve
      })
      const readableProject = {
        id: PROJECT_ID,
        slug: 'edition',
        display_name: 'Readable edition',
        current_user_role: 'viewer',
        current_user_can_manage_members: true,
        working_aggregation_execution_id: null,
        team: {
          id: 'team',
          slug: 'team',
          display_name: 'Team',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        manager_user_id: ACTOR.id,
        created_by_user_id: ACTOR.id,
        created_at: '2026-01-01T00:00:00Z',
      }
      const client = createApiClient({
        fetch: (request) => {
          const path = new URL(request.url).pathname
          if (path === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
          if (path === '/api/v1/me') return Promise.resolve(jsonResponse(ACTOR))
          if (path === '/api/v1/auth/session')
            return Promise.resolve(
              jsonResponse({ must_change_password: false, keep_signed_in: false }),
            )
          if (path === '/api/v1/me/preferences')
            return Promise.resolve(
              jsonResponse({
                locale: 'en',
                theme: 'system',
                desktop_sidebar_collapsed: false,
                revision: 1,
              }),
            )
          if (path === `/api/v1/projects/${PROJECT_ID}/members`) {
            membershipReads += 1
            return transferred
              ? membershipResponse
              : Promise.resolve(
                  jsonResponse({ ...STATE, manager: { ...STATE.manager, project_role: 'viewer' } }),
                )
          }
          if (path === `/api/v1/projects/${PROJECT_ID}`) {
            projectReads += 1
            return transferred ? projectResponse : Promise.resolve(jsonResponse(readableProject))
          }
          if (path === `/api/v1/projects/${PROJECT_ID}/eligible-users`)
            return Promise.resolve(
              jsonResponse({ items: [CANDIDATE], has_more: false, next_cursor: null }),
            )
          if (path === `/api/v1/projects/${PROJECT_ID}/manager` && request.method === 'PUT') {
            transferred = true
            return Promise.resolve(
              jsonResponse({
                ...STATE,
                manager: { ...CANDIDATE, user_id: CANDIDATE.id, project_role: 'operator' },
              }),
            )
          }
          return Promise.resolve(jsonResponse({}, { status: 404 }))
        },
      })
      const wrapper = await mountApplicationAt(`/projects/${PROJECT_ID}/members`, 'en', client)
      await waitFor(() =>
        expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/overview"]`).exists()).toBe(
          true,
        ),
      )
      expect(wrapper.get('aside [aria-current="page"]').text()).toBe('Members')
      await wrapper.get('#transfer').setValue(CANDIDATE.id)
      const transfer = wrapper
        .findAll('main button')
        .find((button) => button.text() === 'Transfer management')
      expect(transfer).toBeDefined()
      await transfer!.trigger('click')
      await waitFor(() => {
        expect(membershipReads).toBe(2)
        expect(projectReads).toBe(2)
      })
      const denyMembership = () =>
        finishMembership(
          jsonResponse(
            {
              error: {
                code: 'resource_not_found',
                message: 'Membership management is no longer available.',
              },
            },
            { status: membershipStatus },
          ),
        )
      const resolveProject = () =>
        finishProject(
          projectStatus === 200
            ? jsonResponse({
                ...readableProject,
                manager_user_id: CANDIDATE.id,
                current_user_can_manage_members: false,
              })
            : jsonResponse(
                {
                  error: { code: 'resource_not_found', message: 'Project is no longer readable.' },
                },
                { status: projectStatus },
              ),
        )
      if (first === 'membership') {
        denyMembership()
        await flushPromises()
        expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/members"]`).exists()).toBe(false)
        expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/overview"]`).exists()).toBe(true)
        resolveProject()
      } else {
        resolveProject()
        await flushPromises()
        denyMembership()
      }
      await waitFor(() => {
        expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/members"]`).exists()).toBe(false)
        expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/overview"]`).exists()).toBe(
          projectStatus === 200,
        )
      })
      expect(wrapper.find('aside nav [aria-current="page"]').exists()).toBe(false)
      expect(wrapper.get('.app-breadcrumbs').text().includes('Readable edition')).toBe(
        projectStatus === 200,
      )
      expect(projectReads).toBe(2)
    },
  )

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
        // Read-only shell requests are not membership writes.
        if (request.method === 'GET') return Promise.resolve(jsonResponse({}, { status: 404 }))
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
    const loadError = wrapper.get('.project-members-load-error')
    expect(loadError.classes()).toContain('app-card')
    expect(loadError.classes()).toContain('app-feedback--critical')
    expect(loadError.findAll('button').map((button) => button.text())).toEqual(['Try again'])
    await loadError.get('button').trigger('click')
    await waitFor(() => expect(wrapper.text()).toContain(MEMBER.display_name))

    // Exercise the recovered state with a rejected membership write.
    const ready = wrapper
    await waitFor(() => expect(ready.text()).toContain(MEMBER.display_name))
    expect(ready.text()).toContain('operator')
    const role = ready.get('tbody select[aria-label="Project role"]')
    for (const [index] of mutationErrors.entries()) {
      await role?.setValue(index % 2 === 0 ? 'operator' : 'reviewer')
      await waitFor(() => expect(mutationAttempts).toBe(index + 1))
      expect(ready.get('main [role="alert"]').text()).toContain('not confirmed')
      expect(ready.get('main .project-members-error').classes()).toContain('app-card')
    }
    await flushPromises()
  })
})
