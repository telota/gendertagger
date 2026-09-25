import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import {
  apiClientWithJsonResponse,
  apiClientWithNetworkError,
  apiClientWithRoutes,
} from '../helpers/api'
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

describe.each(['de', 'en'] as const)('start page in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].publication

  it('shows editors, publisher and publication period when configured', async () => {
    const client = apiClientWithJsonResponse({
      editors: ['Frederike Neuber', 'Lou Klappenbach', 'Tim Westphal'],
      institution_name: 'Berlin-Brandenburgische Akademie der Wissenschaften',
      initiatives: [{ name: 'Gender & Data', url: 'https://gender-data.bbaw.de/' }],
      published_since_year: 2026,
    })
    const page = (await mountApplicationAt('/', locale, client)).get('main')

    const facts = page.get('dl').text()
    expect(page.get('h2').text()).toBe(messages.heading)
    expect(facts).toContain('Frederike Neuber')
    expect(facts).toContain('Berlin-Brandenburgische Akademie der Wissenschaften')
    expect(facts).toContain('Gender & Data')
    expect(facts).toContain(messages.publishedSince.replace('{year}', '2026'))
    expect(page.text()).not.toContain('2.026')
    expect(page.text()).not.toContain('2,026')
  })

  it('lists every editor as a separate item', async () => {
    const client = apiClientWithJsonResponse({ editors: ['Editor One', 'Editor Two'] })
    const page = (await mountApplicationAt('/', locale, client)).get('main')

    const editors = page.get('dl > div:first-child')
    expect(editors.findAll('li').map((item) => item.text())).toEqual(['Editor One', 'Editor Two'])
  })

  it('says publication details are not configured when nothing is', async () => {
    const client = apiClientWithJsonResponse({})
    const page = (await mountApplicationAt('/', locale, client)).get('main')

    expect(page.text()).toContain(messages.notConfigured)
    expect(page.find('dl').exists()).toBe(false)
  })

  it('distinguishes a publication-details fetch failure from an unconfigured deployment', async () => {
    const page = (await mountApplicationAt('/', locale, apiClientWithNetworkError())).get('main')

    expect(page.text()).toContain(messages.loadError)
    expect(page.text()).not.toContain(messages.notConfigured)
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
