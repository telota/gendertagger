import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const SIGNED_IN_ROUTES: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': { body: USER },
  '/api/v1/auth/session': { body: { must_change_password: true, keep_signed_in: false } },
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('change-password page in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].changePassword

  it('renders the current, new and repeat-new password fields', async () => {
    const wrapper = await mountApplicationAt(
      '/change-password',
      locale,
      apiClientWithRoutes(SIGNED_IN_ROUTES),
    )
    await flushPromises()
    const main = wrapper.get('main')

    expect(main.get('h1').text()).toBe(messages.title)
    expect(main.find('input[name="current-password"]').exists()).toBe(true)
    expect(main.find('input[name="new-password"]').exists()).toBe(true)
    expect(main.find('input[name="new-password-repeat"]').exists()).toBe(true)
  })

  it('redirects a signed-out visitor to the login page', async () => {
    const wrapper = await mountApplicationAt(
      '/change-password',
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

    // The login route is lazy; its first import in this test file needs more than one macrotask
    // tick to resolve. See tests/helpers/wait.ts.
    await waitFor(() => {
      expect(wrapper.get('main h1').text()).toBe(catalogues[locale].login.title)
    })
  })

  it('rejects mismatched passwords without calling the server', async () => {
    const wrapper = await mountApplicationAt(
      '/change-password',
      locale,
      apiClientWithRoutes(SIGNED_IN_ROUTES),
    )
    await flushPromises()

    await wrapper.get('input[name="current-password"]').setValue('a-correct-passphrase')
    await wrapper.get('input[name="new-password"]').setValue('a-new-passphrase-1')
    await wrapper.get('input[name="new-password-repeat"]').setValue('a-different-one-1')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(messages.errors.mismatch)
  })

  it('shows an inline error for a wrong current password', async () => {
    const wrapper = await mountApplicationAt(
      '/change-password',
      locale,
      apiClientWithRoutes({
        ...SIGNED_IN_ROUTES,
        '/api/v1/me/password': {
          body: { error: { code: 'invalid_current_password', message: 'Wrong.' } },
          init: { status: 400 },
        },
      }),
    )
    await flushPromises()

    await wrapper.get('input[name="current-password"]').setValue('wrong-passphrase')
    await wrapper.get('input[name="new-password"]').setValue('a-new-passphrase-1')
    await wrapper.get('input[name="new-password-repeat"]').setValue('a-new-passphrase-1')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(messages.errors.invalidCurrentPassword)
  })

  it('shows a validation message when the server rejects the new password', async () => {
    const wrapper = await mountApplicationAt(
      '/change-password',
      locale,
      apiClientWithRoutes({
        ...SIGNED_IN_ROUTES,
        '/api/v1/me/password': {
          body: { error: { code: 'validation_error', message: 'Too short.' } },
          init: { status: 422 },
        },
      }),
    )
    await flushPromises()

    await wrapper.get('input[name="current-password"]').setValue('a-correct-passphrase')
    await wrapper.get('input[name="new-password"]').setValue('too-short')
    await wrapper.get('input[name="new-password-repeat"]').setValue('too-short')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(
      messages.errors.validation.replace('{minLength}', '12'),
    )
  })

  it('succeeds and returns to the start page', async () => {
    const wrapper = await mountApplicationAt(
      '/change-password',
      locale,
      apiClientWithRoutes({
        ...SIGNED_IN_ROUTES,
        '/api/v1/me/password': { body: null, init: { status: 204 } },
      }),
    )
    await flushPromises()

    await wrapper.get('input[name="current-password"]').setValue('a-correct-passphrase')
    await wrapper.get('input[name="new-password"]').setValue('a-new-passphrase-1')
    await wrapper.get('input[name="new-password-repeat"]').setValue('a-new-passphrase-1')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('main h1').text()).toBe(catalogues[locale].app.title)
  })
})
