import { flushPromises, type DOMWrapper } from '@vue/test-utils'
import { getActivePinia } from 'pinia'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import { useSessionStore } from '@/stores/session'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

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
const SETTINGS = {
  revision: 3,
  branding: {
    institution_name: 'Deployment Institute',
    institution_url: 'https://example.test',
    contact_email: 'contact@example.test',
    privacy_notice_url: null,
    editors: ['Deployment Editor'],
    published_since_year: 2025,
    logo_url: null,
    initiatives: [],
    legal_entity: null,
  },
  branding_defaults: {
    institution_name: 'Deployment Institute',
    institution_url: 'https://example.test',
    contact_email: 'contact@example.test',
    privacy_notice_url: null,
    editors: ['Deployment Editor'],
    published_since_year: 2025,
  },
  overridden_fields: ['institution_name'],
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
) {
  return createApiClient({
    fetch: (request: Request) => {
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/me') return Promise.resolve(jsonResponse(currentUser()))
      if (pathname === '/api/v1/auth/session') {
        return Promise.resolve(jsonResponse({ must_change_password: false, keep_signed_in: false }))
      }
      return Promise.resolve(handler(request))
    },
  })
}

function buttonWithText(
  wrapper: { findAll: (selector: string) => DOMWrapper<Element>[] },
  text: string,
) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text() === text)
  if (!button) throw new Error(`Button ${text} was not rendered.`)
  return button
}

async function selectStoreValue(
  wrapper: { get: (selector: string) => { setValue: (value?: unknown) => Promise<void> } },
  field: string,
  value: string,
): Promise<void> {
  await wrapper.get(`input[name="${field}-mode"][value="set"]`).setValue()
  await wrapper.get(`#admin-settings-${field}`).setValue(value)
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)(
  'administrative branding editing in %s',
  (locale: AppLocale) => {
    const messages = catalogues[locale].adminSettings

    it('sends a sparse pinned-value PATCH and refreshes shared public branding after success', async () => {
      const requests: { method: string; pathname: string; body: unknown }[] = []
      const updatedSettings = {
        ...SETTINGS,
        branding: { ...SETTINGS.branding, institution_name: 'Deployment Institute' },
        overridden_fields: ['institution_name'],
      }
      let publicBranding = { institution_name: 'Deployment Institute' }
      const client = signedInClient(
        async (request) => {
          const url = new URL(request.url)
          const body =
            request.method === 'GET' ? null : (JSON.parse(await request.clone().text()) as unknown)
          requests.push({ method: request.method, pathname: url.pathname, body })
          if (url.pathname === '/api/v1/admin/settings' && request.method === 'GET') {
            return jsonResponse(SETTINGS)
          }
          if (url.pathname === '/api/v1/admin/settings' && request.method === 'PATCH') {
            publicBranding = { institution_name: 'Deployment Institute' }
            return jsonResponse(updatedSettings)
          }
          if (url.pathname === '/api/v1/branding') return jsonResponse(publicBranding)
          return jsonResponse({}, { status: 404 })
        },
        () => ADMIN_A,
      )
      const wrapper = await mountApplicationAt('/admin/settings', locale, client)
      await waitFor(() =>
        expect(wrapper.find('#admin-settings-institution_name').exists()).toBe(true),
      )

      await selectStoreValue(wrapper, 'institution_name', 'Deployment Institute')
      await buttonWithText(wrapper, messages.editing.save).trigger('click')
      await waitFor(() =>
        expect(requests).toContainEqual({
          method: 'PATCH',
          pathname: '/api/v1/admin/settings',
          body: {
            expected_revision: 3,
            branding: { institution_name: 'Deployment Institute' },
          },
        }),
      )
      await flushPromises()
      expect(wrapper.text()).toContain('Deployment Institute')
      expect(
        requests.filter(
          ({ method, pathname }) => method === 'GET' && pathname === '/api/v1/branding',
        ),
      ).toHaveLength(2)
    })

    it('keeps clear and reset distinct, confirms reset fallbacks, and never patches all fields', async () => {
      const patchBodies: unknown[] = []
      const resetBodies: unknown[] = []
      const client = signedInClient(
        async (request) => {
          const { pathname } = new URL(request.url)
          if (pathname === '/api/v1/admin/settings' && request.method === 'GET')
            return jsonResponse(SETTINGS)
          if (pathname === '/api/v1/admin/settings' && request.method === 'PATCH') {
            patchBodies.push(JSON.parse(await request.clone().text()) as unknown)
            return jsonResponse({
              ...SETTINGS,
              branding: { ...SETTINGS.branding, contact_email: null },
              revision: 4,
            })
          }
          if (pathname === '/api/v1/admin/settings/reset' && request.method === 'POST') {
            resetBodies.push(JSON.parse(await request.clone().text()) as unknown)
            return jsonResponse({ ...SETTINGS, overridden_fields: [], revision: 5 })
          }
          if (pathname === '/api/v1/branding') return jsonResponse({})
          return jsonResponse({}, { status: 404 })
        },
        () => ADMIN_A,
      )
      const wrapper = await mountApplicationAt('/admin/settings', locale, client)
      await waitFor(() => expect(wrapper.find('#admin-settings-contact_email').exists()).toBe(true))

      await wrapper.get('input[name="contact_email-mode"][value="clear"]').setValue()
      expect(buttonWithText(wrapper, messages.reset.submit).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain(messages.reset.unsavedChanges)
      await wrapper.get('input[name="contact_email-mode"][value="unchanged"]').setValue()
      await wrapper.get('input[name="contact_email-mode"][value="clear"]').setValue()
      await buttonWithText(wrapper, messages.editing.save).trigger('click')
      await waitFor(() =>
        expect(patchBodies).toEqual([{ expected_revision: 3, branding: { contact_email: null } }]),
      )

      await waitFor(() =>
        expect(wrapper.find('#admin-settings-reset-institution_name').exists()).toBe(true),
      )
      await wrapper.get('#admin-settings-reset-institution_name').setValue(true)
      await buttonWithText(wrapper, messages.reset.submit).trigger('click')
      await waitFor(() =>
        expect(wrapper.get('[role="dialog"]').text()).toContain('Deployment Institute'),
      )
      await buttonWithText(wrapper, messages.reset.confirm.submit).trigger('click')
      await waitFor(() =>
        expect(resetBodies).toEqual([{ expected_revision: 4, fields: ['institution_name'] }]),
      )
    })
    it('blocks invalid payloads locally and distinguishes unavailable from uncertain write outcomes', async () => {
      let patchCalls = 0
      let publicBrandingReads = 0
      let writeMode: 'unavailable' | 'lost' = 'unavailable'
      const client = signedInClient(
        (request) => {
          const { pathname } = new URL(request.url)
          if (pathname === '/api/v1/admin/settings' && request.method === 'GET')
            return jsonResponse(SETTINGS)
          if (pathname === '/api/v1/admin/settings' && request.method === 'PATCH') {
            patchCalls += 1
            if (writeMode === 'lost') throw new TypeError('Network lost after submission.')
            return jsonResponse(
              { error: { code: 'settings_unavailable', message: 'Unavailable.' } },
              { status: 503 },
            )
          }
          if (pathname === '/api/v1/branding') {
            publicBrandingReads += 1
            return jsonResponse({})
          }
          return jsonResponse({}, { status: 404 })
        },
        () => ADMIN_A,
      )
      const wrapper = await mountApplicationAt('/admin/settings', locale, client)
      await waitFor(() =>
        expect(wrapper.find('#admin-settings-institution_url').exists()).toBe(true),
      )

      await selectStoreValue(wrapper, 'institution_url', 'not a URL')
      await buttonWithText(wrapper, messages.editing.save).trigger('click')
      expect(patchCalls).toBe(0)
      expect(wrapper.text()).toContain(messages.editing.validation.url)

      await wrapper
        .get('#admin-settings-institution_url')
        .setValue('https://replacement.example.test')
      await buttonWithText(wrapper, messages.editing.save).trigger('click')
      await waitFor(() =>
        expect(wrapper.text()).toContain(messages.editing.errors.settingsUnavailable),
      )
      expect(publicBrandingReads).toBe(1)

      writeMode = 'lost'
      await buttonWithText(wrapper, messages.editing.save).trigger('click')
      await waitFor(() => expect(wrapper.text()).toContain(messages.editing.errors.uncertain))
      expect(publicBrandingReads).toBe(1)
    })

    it('retains a dirty draft after a revision conflict until the administrator explicitly reconciles it', async () => {
      const latest = {
        ...SETTINGS,
        revision: 4,
        branding: { ...SETTINGS.branding, institution_name: 'Other admin' },
      }
      let settingsReads = 0
      const client = signedInClient(
        (request) => {
          const { pathname } = new URL(request.url)
          if (pathname === '/api/v1/admin/settings' && request.method === 'GET') {
            settingsReads += 1
            return jsonResponse(settingsReads === 1 ? SETTINGS : latest)
          }
          if (pathname === '/api/v1/admin/settings' && request.method === 'PATCH') {
            return jsonResponse(
              { error: { code: 'settings_revision_conflict', message: 'Conflict.' } },
              { status: 409 },
            )
          }
          if (pathname === '/api/v1/branding') return jsonResponse({})
          return jsonResponse({}, { status: 404 })
        },
        () => ADMIN_A,
      )
      const wrapper = await mountApplicationAt('/admin/settings', locale, client)
      await waitFor(() =>
        expect(wrapper.find('#admin-settings-institution_name').exists()).toBe(true),
      )

      await selectStoreValue(wrapper, 'institution_name', 'My draft')
      await buttonWithText(wrapper, messages.editing.save).trigger('click')
      await waitFor(() =>
        expect(wrapper.text()).toContain(
          messages.editing.conflict.latestLoaded.replace('{revision}', '4'),
        ),
      )
      expect(
        (wrapper.get('#admin-settings-institution_name').element as HTMLInputElement).value,
      ).toBe('My draft')
      expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()

      await buttonWithText(wrapper, messages.editing.conflict.reconcile).trigger('click')
      expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    })

    it('keeps a late write response private after the principal changes', async () => {
      let currentUser = ADMIN_A
      let resolvePatch: ((response: Response) => void) | undefined
      const client = signedInClient(
        (request) => {
          const { pathname } = new URL(request.url)
          if (pathname === '/api/v1/admin/settings' && request.method === 'GET')
            return jsonResponse(SETTINGS)
          if (pathname === '/api/v1/admin/settings' && request.method === 'PATCH') {
            return new Promise<Response>((resolve) => {
              resolvePatch = resolve
            })
          }
          if (pathname === '/api/v1/branding') return jsonResponse({})
          return jsonResponse({}, { status: 404 })
        },
        () => currentUser,
      )
      const wrapper = await mountApplicationAt('/admin/settings', locale, client)
      await waitFor(() =>
        expect(wrapper.find('#admin-settings-institution_name').exists()).toBe(true),
      )
      await selectStoreValue(wrapper, 'institution_name', 'My draft')
      await buttonWithText(wrapper, messages.editing.save).trigger('click')

      currentUser = ADMIN_B
      await currentSession().initialize()
      resolvePatch?.(jsonResponse({ ...SETTINGS, revision: 4 }))
      await flushPromises()

      expect(wrapper.text()).not.toContain(messages.editing.publicRefreshFailed)
    })
  },
)
