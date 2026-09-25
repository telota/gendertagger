import { flushPromises } from '@vue/test-utils'
import { getActivePinia } from 'pinia'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
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
const OPERATOR = {
  id: 'a0000000-0000-0000-0000-000000000003',
  display_name: 'Operator',
  roles: ['operator'],
}
const SETTINGS = {
  revision: 7,
  branding: {
    institution_name: 'Pinned Institute',
    institution_url: null,
    contact_email: 'pinned@example.test',
    privacy_notice_url: null,
    editors: [],
    published_since_year: 2020,
    logo_url: '/api/v1/branding/logo',
    initiatives: [{ name: 'Research programme', url: 'https://example.test/programme' }],
    legal_entity: {
      name: 'Example Foundation',
      legal_form: 'Foundation',
      address_lines: ['Example Street 1', '12345 Berlin'],
      telephone: '+49 30 123456',
      telephone_href: 'tel:+4930123456',
      representative: 'Example Representative',
      vat_id: 'DE123456789',
    },
  },
  branding_defaults: {
    institution_name: 'Pinned Institute',
    institution_url: 'https://example.test',
    contact_email: 'pinned@example.test',
    privacy_notice_url: null,
    editors: ['Deployment Editor'],
    published_since_year: 2020,
  },
  overridden_fields: ['institution_name', 'institution_url', 'contact_email', 'editors'],
}

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

function signedInClient(
  handler: (request: Request) => Response | Promise<Response>,
  currentUser: () => typeof ADMIN_A,
  mustChangePassword = false,
) {
  return createApiClient({
    fetch: (request: Request) => {
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
      if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(currentUser()))
      if (pathname === '/api/v1/auth/session') {
        return Promise.resolve(
          jsonResponse({ must_change_password: mustChangePassword, keep_signed_in: false }),
        )
      }
      return Promise.resolve(handler(request))
    },
  })
}

function rowFor(
  wrapper: { findAll: (selector: string) => { text: () => string }[] },
  field: string,
) {
  const row = wrapper.findAll('tbody tr').find((candidate) => candidate.text().includes(field))
  if (!row) throw new Error(`No settings row for ${field}.`)
  return row
}

function buttonWithText(
  wrapper: {
    findAll: (
      selector: string,
    ) => { text: () => string; trigger: (event: string) => Promise<void> }[]
  },
  text: string,
) {
  const button = wrapper.findAll('main button').find((candidate) => candidate.text() === text)
  if (!button) throw new Error(`Button ${text} was not rendered.`)
  return button
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('AdminSettingsView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].adminSettings

  it('gates settings navigation and direct access to password-current global administrators', async () => {
    const administrator = await mountApplicationAt(
      '/',
      locale,
      signedInClient(
        () => jsonResponse({}, { status: 404 }),
        () => ADMIN_A,
      ),
    )
    await waitFor(() => {
      expect(administrator.get('aside a[href="/admin/settings"]').text()).toBe(
        catalogues[locale].nav.settings,
      )
    })
    administrator.unmount()

    const operator = await mountApplicationAt(
      '/admin/settings',
      locale,
      signedInClient(
        () => jsonResponse({}, { status: 404 }),
        () => OPERATOR,
      ),
    )
    await flushPromises()
    expect(operator.get('main [role="alert"]').text()).toBe(messages.forbidden)
  })

  it('routes a password-change-required administrator and an unauthenticated visitor away from settings', async () => {
    const passwordChangeRequired = await mountApplicationAt(
      '/admin/settings',
      locale,
      signedInClient(
        () => jsonResponse({}, { status: 404 }),
        () => ADMIN_A,
        true,
      ),
    )
    await waitFor(() => {
      expect(passwordChangeRequired.get('main h1').text()).toBe(
        catalogues[locale].changePassword.title,
      )
    })
    passwordChangeRequired.unmount()

    const signedOut = await mountApplicationAt(
      '/admin/settings',
      locale,
      createApiClient({
        fetch: (request) => {
          const { pathname } = new URL(request.url)
          if (pathname === '/api/v1/branding') return Promise.resolve(jsonResponse({}))
          if (pathname === '/api/v1/me') {
            return Promise.resolve(
              jsonResponse(
                {
                  error: {
                    code: 'authentication_required',
                    message: 'Authentication is required.',
                  },
                },
                { status: 401 },
              ),
            )
          }
          return Promise.resolve(jsonResponse({}, { status: 404 }))
        },
      }),
    )
    await waitFor(() =>
      expect(signedOut.get('main h1').text()).toBe(catalogues[locale].login.title),
    )
  })

  it('renders effective values, fallbacks, explicit clearings, and equal-valued overrides', async () => {
    const wrapper = await mountApplicationAt(
      '/admin/settings',
      locale,
      signedInClient(
        (request) => {
          if (new URL(request.url).pathname === '/api/v1/admin/settings') {
            return jsonResponse(SETTINGS)
          }
          return jsonResponse({}, { status: 404 })
        },
        () => ADMIN_A,
      ),
    )
    await waitFor(() => expect(wrapper.find('table').exists()).toBe(true))

    expect(rowFor(wrapper, messages.fields.institutionName).text()).toContain(
      messages.status.overridden,
    )
    expect(rowFor(wrapper, messages.fields.institutionUrl).text()).toContain(
      messages.status.cleared,
    )
    expect(rowFor(wrapper, messages.fields.institutionUrl).text()).toContain('https://example.test')
    expect(rowFor(wrapper, messages.fields.contactEmail).text()).toContain(
      messages.status.overridden,
    )
    expect(rowFor(wrapper, messages.fields.privacyNoticeUrl).text()).toContain(
      messages.status.inherited,
    )
    expect(rowFor(wrapper, messages.fields.editors).text()).toContain(messages.status.cleared)
    expect(rowFor(wrapper, messages.fields.editors).text()).toContain(messages.values.noEditors)
    expect(rowFor(wrapper, messages.fields.publishedSinceYear).text()).toContain(
      messages.status.inherited,
    )
    expect(wrapper.text()).toContain(SETTINGS.branding.logo_url)
    expect(wrapper.text()).toContain(SETTINGS.branding.initiatives[0]?.name)
    expect(wrapper.text()).toContain(SETTINGS.branding.legal_entity.name)
    expect(wrapper.text()).toContain(messages.editingAvailable)
    await expectNoAxeViolations(wrapper.element)
  })

  it('distinguishes an unavailable settings store from an ordinary fetch error and retries explicitly', async () => {
    let requests = 0
    const client = signedInClient(
      (request) => {
        if (new URL(request.url).pathname !== '/api/v1/admin/settings') {
          return jsonResponse({}, { status: 404 })
        }
        requests += 1
        if (requests === 1) {
          return jsonResponse(
            { error: { code: 'settings_unavailable', message: 'Unavailable.' } },
            { status: 503 },
          )
        }
        return jsonResponse(SETTINGS)
      },
      () => ADMIN_A,
    )
    const wrapper = await mountApplicationAt('/admin/settings', locale, client)
    await waitFor(() =>
      expect(wrapper.get('main [role="alert"]').text()).toBe(messages.settingsUnavailable),
    )

    await buttonWithText(wrapper, messages.retry).trigger('click')
    await waitFor(() => expect(wrapper.find('table').exists()).toBe(true))
    expect(requests).toBe(2)
  })

  it('shows an ordinary fetch error without presenting deployment defaults', async () => {
    const wrapper = await mountApplicationAt(
      '/admin/settings',
      locale,
      signedInClient(
        (request) => {
          if (new URL(request.url).pathname === '/api/v1/admin/settings') {
            return jsonResponse(
              { error: { code: 'internal_error', message: 'Failed.' } },
              { status: 500 },
            )
          }
          return jsonResponse({}, { status: 404 })
        },
        () => ADMIN_A,
      ),
    )
    await waitFor(() => expect(wrapper.get('main [role="alert"]').text()).toBe(messages.loadError))
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('removes a former principal settings response before rendering the next administrator data', async () => {
    let currentUser = ADMIN_A
    let resolveFormerSettings: ((response: Response) => void) | undefined
    const currentSettings = {
      ...SETTINGS,
      branding: { ...SETTINGS.branding, institution_name: 'Current administrator branding' },
      branding_defaults: { ...SETTINGS.branding_defaults, institution_name: 'Current fallback' },
    }
    const client = signedInClient(
      (request) => {
        if (new URL(request.url).pathname !== '/api/v1/admin/settings') {
          return jsonResponse({}, { status: 404 })
        }
        if (currentUser.id === ADMIN_A.id) {
          return new Promise<Response>((resolve) => {
            resolveFormerSettings = resolve
          })
        }
        return jsonResponse(currentSettings)
      },
      () => currentUser,
    )
    const wrapper = await mountApplicationAt('/admin/settings', locale, client)
    await flushPromises()

    currentUser = ADMIN_B
    await currentSession().initialize()
    await waitFor(() => expect(wrapper.text()).toContain('Current administrator branding'))

    resolveFormerSettings?.(jsonResponse(SETTINGS))
    await flushPromises()
    expect(wrapper.text()).not.toContain(SETTINGS.branding.institution_name)
    expect(wrapper.text()).toContain('Current administrator branding')
  })
})
