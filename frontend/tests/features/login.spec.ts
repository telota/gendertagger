import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import {
  apiClientWithRoutes,
  apiClientWithRoutesAndOneUnreachablePath,
  type RouteResponse,
} from '../helpers/api'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const SIGNED_OUT_ROUTES: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': {
    body: { error: { code: 'authentication_required', message: 'Authentication is required.' } },
    init: { status: 401 },
  },
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('login page in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].login

  it('renders username, password and a keep-signed-in checkbox', async () => {
    const wrapper = await mountApplicationAt(
      '/login',
      locale,
      apiClientWithRoutes(SIGNED_OUT_ROUTES),
    )
    const main = wrapper.get('main')

    expect(main.get('h1').text()).toBe(messages.title)
    expect(main.find('input[name="username"]').exists()).toBe(true)
    expect(main.get('input[name="password"]').attributes('type')).toBe('password')
    expect(main.find('input[type="checkbox"]').exists()).toBe(true)
  })

  it('signs in and lands on the start page, showing the signed-in header', async () => {
    const wrapper = await mountApplicationAt(
      '/login',
      locale,
      apiClientWithRoutes({
        ...SIGNED_OUT_ROUTES,
        '/api/v1/auth/login': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
      }),
    )

    await wrapper.get('input[name="username"]').setValue('reviewer.one')
    await wrapper.get('input[name="password"]').setValue('a-correct-passphrase')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('main .login-form').exists()).toBe(false)
    expect(wrapper.get('header').text()).toContain('Reviewer One')
  })

  it('redirects to the forced password change when the session requires it', async () => {
    const wrapper = await mountApplicationAt(
      '/login',
      locale,
      apiClientWithRoutes({
        ...SIGNED_OUT_ROUTES,
        '/api/v1/auth/login': { body: USER },
        '/api/v1/auth/session': { body: { must_change_password: true, keep_signed_in: false } },
      }),
    )

    await wrapper.get('input[name="username"]').setValue('reviewer.one')
    await wrapper.get('input[name="password"]').setValue('a-correct-passphrase')
    await wrapper.get('form').trigger('submit')

    // The change-password route is lazy; its first import in this test file needs more than one
    // macrotask tick to resolve. See tests/helpers/wait.ts.
    await waitFor(() => {
      expect(wrapper.get('main h1').text()).toBe(catalogues[locale].changePassword.title)
    })
  })

  it('shows an inline error for wrong credentials without navigating away', async () => {
    const wrapper = await mountApplicationAt(
      '/login',
      locale,
      apiClientWithRoutes({
        ...SIGNED_OUT_ROUTES,
        '/api/v1/auth/login': {
          body: { error: { code: 'invalid_credentials', message: 'Wrong.' } },
          init: { status: 401 },
        },
      }),
    )

    await wrapper.get('input[name="username"]').setValue('reviewer.one')
    await wrapper.get('input[name="password"]').setValue('wrong')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(messages.errors.invalidCredentials)
    expect(wrapper.get('main h1').text()).toBe(messages.title)
  })

  it('shows a network-error message when the server cannot be reached', async () => {
    const wrapper = await mountApplicationAt(
      '/login',
      locale,
      apiClientWithRoutesAndOneUnreachablePath(SIGNED_OUT_ROUTES, '/api/v1/auth/login'),
    )

    await wrapper.get('input[name="username"]').setValue('reviewer.one')
    await wrapper.get('input[name="password"]').setValue('whatever')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(messages.errors.network)
  })

  it('shows a rate-limit message when the gateway throttles repeated attempts', async () => {
    const wrapper = await mountApplicationAt(
      '/login',
      locale,
      apiClientWithRoutes({
        ...SIGNED_OUT_ROUTES,
        '/api/v1/auth/login': {
          body: { error: { code: 'rate_limited', message: 'Too many attempts.' } },
          init: { status: 429 },
        },
      }),
    )

    await wrapper.get('input[name="username"]').setValue('reviewer.one')
    await wrapper.get('input[name="password"]').setValue('whatever')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(messages.errors.rateLimited)
  })

  it('shows a validation message when the server rejects the submitted fields', async () => {
    const wrapper = await mountApplicationAt(
      '/login',
      locale,
      apiClientWithRoutes({
        ...SIGNED_OUT_ROUTES,
        '/api/v1/auth/login': {
          body: { error: { code: 'validation_error', message: 'Invalid.' } },
          init: { status: 422 },
        },
      }),
    )

    await wrapper.get('input[name="username"]').setValue('Not A Valid Username')
    await wrapper.get('input[name="password"]').setValue('whatever')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(messages.errors.validation)
  })
})
