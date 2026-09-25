import { flushPromises, type VueWrapper } from '@vue/test-utils'
// jsdom's own `File` cannot be read by Vitest's Node-`fetch`-compat layer when it ends up inside a
// `FormData` body (`Cannot read properties of undefined (reading '_buffer')` deep inside undici's
// `makeCompatFormData`, constructing openapi-fetch's internal `Request`) — a jsdom/Vitest/undici
// interop gap in the test environment only; a real browser's own `File` has no such conflict.
import { File as NodeFile } from 'node:buffer'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../../helpers/api'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function testFile(content: string, name: string, type: string): File {
  return new NodeFile([content], name, { type }) as unknown as File
}

function selectFile(wrapper: VueWrapper, selector: string, file: File): void {
  const input = wrapper.get(selector).element as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  input.dispatchEvent(new Event('change'))
}

const catalogues = { de, en } as const

const VIEWER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Viewer One', roles: [] }
const OPERATOR = {
  id: 'a0000000-0000-0000-0000-000000000002',
  display_name: 'Operator One',
  roles: [],
}
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'

function projectFor(role: string) {
  return {
    id: PROJECT_ID,
    slug: 'project-a',
    display_name: 'Project A',
    description: null,
    current_user_role: role,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function pendingSnapshot() {
  return {
    id: SNAPSHOT_ID,
    project_id: PROJECT_ID,
    source_artifact_id: 'd0000000-0000-0000-0000-000000000001',
    source_sha256: 'a'.repeat(64),
    parser_version: '1',
    status: 'pending',
    created_at: '2026-01-01T00:00:00Z',
  }
}

function signedInRoutes(user: typeof VIEWER, role: string): Record<string, RouteResponse> {
  return {
    '/api/v1/branding': { body: {} },
    '/api/v1/me': { body: user },
    '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    [`/api/v1/projects/${PROJECT_ID}`]: { body: projectFor(role) },
  }
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('ImportView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projects.import

  it('tells a non-operator that import is not theirs to do', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/import`,
      locale,
      apiClientWithRoutes(signedInRoutes(VIEWER, 'viewer')),
    )
    await flushPromises()

    expect(wrapper.text()).toContain(messages.forbidden)
    expect(wrapper.find('#import-file').exists()).toBe(false)
  })

  it('shows a load error and retries when the project fails to load', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/import`,
      locale,
      apiClientWithRoutes({
        ...signedInRoutes(OPERATOR, 'operator'),
        [`/api/v1/projects/${PROJECT_ID}`]: {
          body: { error: { code: 'resource_not_found', message: 'Gone.' } },
          init: { status: 404 },
        },
      }),
    )
    await flushPromises()

    expect(wrapper.get('main').text()).toContain(catalogues[locale].projects.overview.loadError)
  })

  it('uploads a file with a chosen source format and shows the import as running', async () => {
    let capturedSourceFormat: FormDataEntryValue | null = null
    const client = createApiClient({
      fetch: async (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return jsonResponse({})
        if (pathname === '/api/v1/me') return jsonResponse(OPERATOR)
        if (pathname === '/api/v1/auth/session') {
          return jsonResponse({ must_change_password: false, keep_signed_in: false })
        }
        if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
          return jsonResponse(projectFor('operator'))
        }
        if (pathname === `/api/v1/projects/${PROJECT_ID}/snapshots`) {
          capturedSourceFormat = (await request.formData()).get('source_format')
          return jsonResponse(pendingSnapshot(), { status: 202 })
        }
        if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}`) {
          return jsonResponse(pendingSnapshot())
        }
        return jsonResponse({}, { status: 404 })
      },
    })
    const wrapper = await mountApplicationAt(`/projects/${PROJECT_ID}/import`, locale, client)
    await flushPromises()

    const formatSwitcher = wrapper.get('.import-format')
    await formatSwitcher.get('button').trigger('click')
    const csvOption = formatSwitcher.findAll('li').find((item) => item.text() === 'CSV')
    await csvOption?.trigger('click')
    selectFile(wrapper, '#import-file', testFile('<TEI/>', 'source.xml', 'text/xml'))
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(messages.status.pending)
    expect(capturedSourceFormat).toBe('csv')
  })

  it('shows the record count once the import is ready', async () => {
    const client = createApiClient({
      fetch: (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(OPERATOR))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
          return Promise.resolve(jsonResponse(projectFor('operator')))
        }
        if (pathname === `/api/v1/projects/${PROJECT_ID}/snapshots`) {
          return Promise.resolve(jsonResponse(pendingSnapshot(), { status: 202 }))
        }
        if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}`) {
          return Promise.resolve(
            jsonResponse({ ...pendingSnapshot(), status: 'ready', record_count: 42 }),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt(`/projects/${PROJECT_ID}/import`, locale, client)
    await flushPromises()

    selectFile(wrapper, '#import-file', testFile('a,b', 'source.csv', 'text/csv'))
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(messages.status.ready.replace('{count}', '42'))
    expect(wrapper.get('.import-status-provenance').text()).toContain('a'.repeat(64))
    expect(wrapper.get(`main a[href="/projects/${PROJECT_ID}/overview"]`).text()).toBe(
      messages.status.toOverview,
    )
  })

  it('shows the failure diagnostic once the import fails', async () => {
    const client = createApiClient({
      fetch: (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(OPERATOR))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
          return Promise.resolve(jsonResponse(projectFor('operator')))
        }
        if (pathname === `/api/v1/projects/${PROJECT_ID}/snapshots`) {
          return Promise.resolve(jsonResponse(pendingSnapshot(), { status: 202 }))
        }
        if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}`) {
          return Promise.resolve(
            jsonResponse({
              ...pendingSnapshot(),
              status: 'failed',
              failure_diagnostic: 'Unrecognised encoding.',
            }),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt(`/projects/${PROJECT_ID}/import`, locale, client)
    await flushPromises()

    selectFile(wrapper, '#import-file', testFile('x', 'source.xml', 'text/xml'))
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Unrecognised encoding.')
  })

  it('shows the size-limit error inline and keeps the form open', async () => {
    const client = createApiClient({
      fetch: (request) => {
        const { pathname } = new URL(request.url)
        if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
        if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(OPERATOR))
        if (pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            jsonResponse({ must_change_password: false, keep_signed_in: false }),
          )
        }
        if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
          return Promise.resolve(jsonResponse(projectFor('operator')))
        }
        if (pathname === `/api/v1/projects/${PROJECT_ID}/snapshots`) {
          return Promise.resolve(
            jsonResponse(
              { error: { code: 'payload_too_large', message: 'Too big.' } },
              { status: 413 },
            ),
          )
        }
        return Promise.resolve(jsonResponse({}, { status: 404 }))
      },
    })
    const wrapper = await mountApplicationAt(`/projects/${PROJECT_ID}/import`, locale, client)
    await flushPromises()

    selectFile(wrapper, '#import-file', testFile('x', 'source.xml', 'text/xml'))
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('main [role="alert"]').text()).toBe(messages.errors.tooLarge)
    expect(wrapper.find('#import-file').exists()).toBe(true)
  })

  it('redirects a signed-out visitor to the login page', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/import`,
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
})
