import { flushPromises } from '@vue/test-utils'
import { getActivePinia } from 'pinia'
import { afterEach, describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import { createAppRouter } from '@/app/router'
import { useSessionStore } from '@/stores/session'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const
const ADMIN_A = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Admin A',
  roles: ['admin'],
}
const ADMIN_B = {
  id: 'a0000000-0000-0000-0000-000000000002',
  display_name: 'Admin B',
  roles: ['admin'],
}
const ACCOUNT = {
  id: 'b0000000-0000-0000-0000-000000000001',
  username: 'alpha',
  display_name: 'Alpha Account',
  roles: ['admin'],
  is_active: true,
  must_change_password: false,
  created_at: '2026-09-24T00:00:00Z',
}

const ADMIN_ACCOUNT_TEST = 'administrative account management in %s'
const CREATE_ACCOUNT_TEST =
  'creates an account with the exact canonical body, accepts empty roles, and preserves the password disclosure through a directory refresh'
const UPDATE_ACCOUNT_TEST =
  'only patches changed mutable fields, preserves the immutable username, and sends an empty replacement role set'
const DUPLICATE_SUBMISSION_TEST =
  'prevents duplicate creation submissions and shows the canonical conflict message'
const DEACTIVATION_TEST =
  'confirms deactivation and disables the self-lockout controls with their explanations'
const LATE_RESPONSE_TEST = 'clears a late temporary-password response after the principal changes'
const DISPOSED_RESPONSE_TEST =
  'ignores a late create response after the administrative view is disposed'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function currentSession() {
  const pinia = getActivePinia()
  if (!pinia) throw new Error('The mounted application must install Pinia.')
  return useSessionStore(pinia)
}

function buttonWithText(
  wrapper: {
    findAll: (
      selector: string,
    ) => { text: () => string; trigger: (event: string) => Promise<void> }[]
  },
  text: string,
) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text() === text)
  if (!button) throw new Error(`Button ${text} was not rendered.`)
  return button
}

function signedInClient(
  handler: (request: Request) => Response | Promise<Response>,
  currentUser: () => typeof ADMIN_A,
) {
  return createApiClient({
    fetch: (request: Request) => {
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
      if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(currentUser()))
      if (pathname === '/api/v1/auth/session') {
        return Promise.resolve(jsonResponse({ must_change_password: false, keep_signed_in: false }))
      }
      return Promise.resolve(handler(request))
    },
  })
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)(ADMIN_ACCOUNT_TEST, (locale: AppLocale) => {
  const messages = catalogues[locale].admin
  it(CREATE_ACCOUNT_TEST, async () => {
    const requests: { pathname: string; body: unknown }[] = []
    let directoryRequests = 0
    const client = signedInClient(
      async (request) => {
        const url = new URL(request.url)
        const body =
          request.method === 'GET' ? null : (JSON.parse(await request.clone().text()) as unknown)
        requests.push({ pathname: url.pathname, body })
        if (url.pathname === '/api/v1/admin/users' && request.method === 'GET') {
          directoryRequests += 1
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        if (url.pathname === '/api/v1/admin/users' && request.method === 'POST') {
          return jsonResponse(
            { account: ACCOUNT, temporary_password: 'temporary-password-only-once' },
            { status: 201 },
          )
        }
        return jsonResponse({}, { status: 404 })
      },
      () => ADMIN_A,
    )
    const wrapper = await mountApplicationAt('/admin/users', locale, client)
    await waitFor(() => expect(wrapper.find('#admin-user-create-username').exists()).toBe(true))
    await wrapper.get('#admin-user-create-username').setValue('New.Admin')
    await wrapper.get('#admin-user-create-display-name').setValue('New administrator')
    await buttonWithText(wrapper, messages.creation.submit).trigger('click')

    await waitFor(() => expect(wrapper.text()).toContain('temporary-password-only-once'))
    expect(
      requests.filter(
        (request) => request.pathname === '/api/v1/admin/users' && request.body !== null,
      ),
    ).toEqual([
      {
        pathname: '/api/v1/admin/users',
        body: { username: 'New.Admin', display_name: 'New administrator', roles: [] },
      },
    ])
    await waitFor(() => expect(directoryRequests).toBeGreaterThan(1))
    expect(currentSession().user?.display_name).not.toContain('temporary-password-only-once')
    expect(document.cookie).not.toContain('temporary-password-only-once')
    await expectNoAxeViolations(wrapper.element)
  })

  it(UPDATE_ACCOUNT_TEST, async () => {
    const patchBodies: unknown[] = []
    const client = signedInClient(
      async (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/admin/users' && request.method === 'GET') {
          return jsonResponse({ items: [ACCOUNT], has_more: false, next_cursor: null })
        }
        if (pathname === `/api/v1/admin/users/${ACCOUNT.id}` && request.method === 'PATCH') {
          patchBodies.push(JSON.parse(await request.clone().text()) as unknown)
          return jsonResponse({ ...ACCOUNT, roles: [] })
        }
        return jsonResponse({}, { status: 404 })
      },
      () => ADMIN_A,
    )
    const wrapper = await mountApplicationAt('/admin/users', locale, client)
    await waitFor(() => expect(wrapper.text()).toContain(ACCOUNT.username))

    await buttonWithText(wrapper, messages.editing.open).trigger('click')
    expect(wrapper.get(`#admin-user-edit-username-${ACCOUNT.id}`).element).toHaveProperty(
      'readOnly',
      true,
    )
    await wrapper.get(`#admin-user-edit-role-${ACCOUNT.id}-admin`).setValue(false)
    await buttonWithText(wrapper, messages.editing.save).trigger('click')

    await waitFor(() => expect(patchBodies).toEqual([{ roles: [] }]))
  })

  it(DUPLICATE_SUBMISSION_TEST, async () => {
    let resolveCreate: ((response: Response) => void) | undefined
    let createRequests = 0
    const client = signedInClient(
      (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/admin/users' && request.method === 'GET') {
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        if (pathname === '/api/v1/admin/users' && request.method === 'POST') {
          createRequests += 1
          return new Promise<Response>((resolve) => {
            resolveCreate = resolve
          })
        }
        return jsonResponse({}, { status: 404 })
      },
      () => ADMIN_A,
    )
    const wrapper = await mountApplicationAt('/admin/users', locale, client)
    await waitFor(() => expect(wrapper.find('#admin-user-create-username').exists()).toBe(true))
    await wrapper.get('#admin-user-create-username').setValue('new.admin')
    await wrapper.get('#admin-user-create-display-name').setValue('New administrator')

    const createButton = buttonWithText(wrapper, messages.creation.submit)
    await createButton.trigger('click')
    await createButton.trigger('click')
    expect(createRequests).toBe(1)

    resolveCreate?.(
      jsonResponse({ error: { code: 'username_conflict', message: 'Taken.' } }, { status: 409 }),
    )
    await waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe(messages.errors.usernameConflict),
    )
  })

  it(DEACTIVATION_TEST, async () => {
    const patchBodies: unknown[] = []
    const currentAccount = { ...ACCOUNT, id: ADMIN_A.id, username: 'admin.a' }
    const client = signedInClient(
      async (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/admin/users' && request.method === 'GET') {
          return jsonResponse({
            items: [ACCOUNT, currentAccount],
            has_more: false,
            next_cursor: null,
          })
        }
        if (pathname === `/api/v1/admin/users/${ACCOUNT.id}` && request.method === 'PATCH') {
          return jsonResponse({ ...ACCOUNT, is_active: false })
        }
        return jsonResponse({}, { status: 404 })
      },
      () => ADMIN_A,
    )
    const wrapper = await mountApplicationAt('/admin/users', locale, client)
    await waitFor(() => expect(wrapper.text()).toContain(ACCOUNT.username))

    await buttonWithText(wrapper, messages.editing.open).trigger('click')
    await wrapper.get(`#admin-user-edit-active-${ACCOUNT.id}`).setValue(false)
    await buttonWithText(wrapper, messages.editing.save).trigger('click')
    await waitFor(() =>
      expect(wrapper.get('[role="dialog"]').text()).toContain(messages.deactivation.sessions),
    )
    await buttonWithText(wrapper, messages.deactivation.confirm).trigger('click')
    await waitFor(() => expect(patchBodies).toEqual([{ is_active: false }]))

    await buttonWithText(wrapper, messages.editing.open).trigger('click')
    await buttonWithText(wrapper, messages.editing.cancel).trigger('click')
    const editButtons = wrapper
      .findAll('button')
      .filter((button) => button.text() === messages.editing.open)
    await editButtons.at(-1)?.trigger('click')
    expect(
      wrapper.get(`#admin-user-edit-active-${ADMIN_A.id}`).attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.get(`#admin-user-edit-role-${ADMIN_A.id}-admin`).attributes('disabled'),
    ).toBeDefined()
    expect(wrapper.text()).toContain(messages.editing.selfDeactivationLocked)
    expect(wrapper.text()).toContain(messages.editing.selfAdminRoleLocked)
  })

  it(LATE_RESPONSE_TEST, async () => {
    let currentUser = ADMIN_A
    let resolveCreate: ((response: Response) => void) | undefined
    const client = signedInClient(
      (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/admin/users' && request.method === 'GET') {
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        if (pathname === '/api/v1/admin/users' && request.method === 'POST') {
          return new Promise<Response>((resolve) => {
            resolveCreate = resolve
          })
        }
        return jsonResponse({}, { status: 404 })
      },
      () => currentUser,
    )
    const wrapper = await mountApplicationAt('/admin/users', locale, client)
    await waitFor(() => expect(wrapper.find('#admin-user-create-username').exists()).toBe(true))
    await wrapper.get('#admin-user-create-username').setValue('new.admin')
    await wrapper.get('#admin-user-create-display-name').setValue('New administrator')
    await buttonWithText(wrapper, messages.creation.submit).trigger('click')

    currentUser = ADMIN_B
    await currentSession().initialize()
    resolveCreate?.(
      jsonResponse(
        { account: ACCOUNT, temporary_password: 'must-not-survive-principal-change' },
        { status: 201 },
      ),
    )
    await flushPromises()

    expect(wrapper.text()).not.toContain('must-not-survive-principal-change')
    expect(currentSession().user?.id).toBe(ADMIN_B.id)
  })

  it(DISPOSED_RESPONSE_TEST, async () => {
    let resolveCreate: ((response: Response) => void) | undefined
    let directoryRequests = 0
    const client = signedInClient(
      (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/admin/users' && request.method === 'GET') {
          directoryRequests += 1
          return jsonResponse({ items: [], has_more: false, next_cursor: null })
        }
        if (pathname === '/api/v1/admin/users' && request.method === 'POST') {
          return new Promise<Response>((resolve) => {
            resolveCreate = resolve
          })
        }
        return jsonResponse({}, { status: 404 })
      },
      () => ADMIN_A,
    )
    const router = createAppRouter(createMemoryHistory())
    const wrapper = await mountApplicationAt('/admin/users', locale, client, router)
    await waitFor(() => expect(wrapper.find('#admin-user-create-username').exists()).toBe(true))
    await wrapper.get('#admin-user-create-username').setValue('new.admin')
    await wrapper.get('#admin-user-create-display-name').setValue('New administrator')
    await buttonWithText(wrapper, messages.creation.submit).trigger('click')

    await router.push('/')
    await flushPromises()
    resolveCreate?.(
      jsonResponse(
        { account: ACCOUNT, temporary_password: 'must-not-survive-view-disposal' },
        { status: 201 },
      ),
    )
    await flushPromises()

    expect(wrapper.text()).not.toContain('must-not-survive-view-disposal')
    expect(directoryRequests).toBe(1)
  })
})
