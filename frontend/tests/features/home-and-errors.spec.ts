import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithJsonResponse, apiClientWithRoutes } from '../helpers/api'
import { mountApplicationAt } from '../helpers/render'

const catalogues = { de, en } as const

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('home page in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].home

  it('greets a signed-out visitor with the guest introduction and a sign-in link', async () => {
    const page = (await mountApplicationAt('/', locale, apiClientWithJsonResponse({}))).get('main')

    expect(page.text()).toContain(messages.guest.lede)
    expect(page.get('a[href="/login"]').text()).toBe(messages.guest.signIn)
    expect(page.findAll('ol > li')).toHaveLength(3)
  })

  it('welcomes a signed-in visitor by name and links to their projects', async () => {
    const user = {
      id: 'a0000000-0000-0000-0000-000000000009',
      display_name: 'Ada Lovelace',
      roles: [] as string[],
    }
    const wrapper = await mountApplicationAt(
      '/',
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': { body: user },
        '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
      }),
    )
    await flushPromises()
    const page = wrapper.get('main')

    expect(page.text()).toContain(
      messages.signedIn.welcomeBack.replace('{name}', user.display_name),
    )
    expect(page.get('a[href="/projects"]').text()).toBe(messages.signedIn.goToProjects)
  })
})

describe.each(['de', 'en'] as const)('page not found in %s', (locale: AppLocale) => {
  it('explains the miss and links back to the start page', async () => {
    const client = apiClientWithJsonResponse({})
    const page = (await mountApplicationAt('/gibt-es-nicht', locale, client)).get('main')
    const messages = catalogues[locale].notFound

    expect(page.get('h1').text()).toBe(messages.title)
    expect(page.get('a[href="/"]').text()).toBe(messages.backToStart)
  })
})
