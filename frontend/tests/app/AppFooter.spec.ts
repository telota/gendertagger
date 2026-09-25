import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient, type ApiClient } from '@/api'
import AppFooter from '@/app/AppFooter.vue'
import { createAppI18n, type AppLocale } from '@/app/i18n'
import { SOURCE_CODE_LICENSE } from '@/app/publication'
import { createQueryClient } from '@/app/queryClient'
import { createAppRouter } from '@/app/router'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithJsonResponse, apiClientWithNetworkError } from '../helpers/api'

const catalogues = { de, en } as const

async function renderFooter(locale: AppLocale, client: ApiClient) {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  await router.isReady()
  const wrapper = mount(AppFooter, {
    global: {
      plugins: [
        createAppI18n(locale),
        router,
        [VueQueryPlugin, { queryClient: createQueryClient() }],
      ],
      provide: { [API_CLIENT_KEY as symbol]: client },
    },
  })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('AppFooter in %s', (locale) => {
  const messages = catalogues[locale].footer
  const publicationMessages = catalogues[locale].publication

  it('shows configured publication metadata and an ungrouped publication year', async () => {
    const footer = await renderFooter(
      locale,
      apiClientWithJsonResponse({
        editors: ['Frederike Neuber', 'Lou Klappenbach', 'Tim Westphal'],
        institution_name: 'Berlin-Brandenburgische Akademie der Wissenschaften',
        institution_url: 'https://www.bbaw.de/',
        initiatives: [{ name: 'Gender & Data', url: 'https://gender-data.bbaw.de/' }],
        published_since_year: 2026,
      }),
    )

    const publication = footer.get('section[aria-labelledby="publication-heading"]')
    const facts = publication.get('dl').text()
    expect(publication.get('h2#publication-heading').text()).toBe(publicationMessages.heading)
    expect(facts).toContain(publicationMessages.editors)
    expect(facts).toContain('Frederike Neuber')
    expect(facts).toContain(messages.publisher)
    expect(facts).toContain(messages.initiatives)
    expect(facts).toContain(publicationMessages.published)
    expect(facts).toContain(publicationMessages.publishedSince.replace('{year}', '2026'))
    expect(publication.text()).not.toContain('2.026')
    expect(publication.text()).not.toContain('2,026')
    expect(publication.text()).not.toContain(publicationMessages.notConfigured)

    const link = publication.get('a[href="https://www.bbaw.de/"]')
    expect(link.text()).toBe('Berlin-Brandenburgische Akademie der Wissenschaften')
    expect(footer.findAll('a[href="https://www.bbaw.de/"]')).toHaveLength(1)
    expect(publication.get('a[href="https://gender-data.bbaw.de/"]').text()).toBe('Gender & Data')
    expect(footer.findAll('a[href="https://gender-data.bbaw.de/"]')).toHaveLength(1)
  })

  it('lists every editor as a separate item', async () => {
    const footer = await renderFooter(
      locale,
      apiClientWithJsonResponse({ editors: ['Editor One', 'Editor Two'] }),
    )

    const publication = footer.get('section[aria-labelledby="publication-heading"]')
    expect(publication.findAll('dl li').map((item) => item.text())).toEqual([
      'Editor One',
      'Editor Two',
    ])
  })

  it('shows the publisher name as plain text when no URL is configured', async () => {
    const footer = await renderFooter(
      locale,
      apiClientWithJsonResponse({ institution_name: 'BBAW' }),
    )

    const publisher = footer.get('.app-footer-publisher')
    expect(publisher.find('a').exists()).toBe(false)
    expect(publisher.text()).toBe('BBAW')
  })

  it('shows a configured logo as a decorative image beside the publisher name', async () => {
    const footer = await renderFooter(
      locale,
      apiClientWithJsonResponse({
        institution_name: 'BBAW',
        logo_url: '/api/v1/branding/logo',
      }),
    )

    const logo = footer.get('img')
    expect(logo.attributes('src')).toBe('/api/v1/branding/logo')
    expect(logo.attributes('alt')).toBe('')
  })

  it('lists configured initiatives, linked by name', async () => {
    const footer = await renderFooter(
      locale,
      apiClientWithJsonResponse({
        initiatives: [{ name: 'Gender & Data', url: 'https://gender-data.bbaw.de/' }],
      }),
    )

    const publication = footer.get('section[aria-labelledby="publication-heading"]')
    expect(publication.text()).toContain(messages.initiatives)
    expect(publication.get('a[href="https://gender-data.bbaw.de/"]').text()).toBe('Gender & Data')
  })

  it('offers the configured contact address', async () => {
    const footer = await renderFooter(
      locale,
      apiClientWithJsonResponse({ contact_email: 'telota@bbaw.de' }),
    )

    expect(footer.get('a[href="mailto:telota@bbaw.de"]').text()).toBe('telota@bbaw.de')
  })

  it('always states the source-code licence and links to its text', async () => {
    const footer = await renderFooter(locale, apiClientWithJsonResponse({}))

    const link = footer.get(`a[href="${SOURCE_CODE_LICENSE.url}"]`)
    expect(link.text()).toContain(SOURCE_CODE_LICENSE.name)
    expect(footer.text()).toContain(messages.license)
  })

  it('always links the internal legal notice route', async () => {
    const footer = await renderFooter(locale, apiClientWithJsonResponse({}))

    const navigation = footer.get(`nav[aria-label="${messages.legalNavigation}"]`)
    expect(navigation.get('a[href="/impressum"]').text()).toBe(messages.legalNotice)
  })

  it('links the configured privacy notice', async () => {
    const footer = await renderFooter(
      locale,
      apiClientWithJsonResponse({ privacy_notice_url: 'https://www.bbaw.de/datenschutz' }),
    )

    const navigation = footer.get(`nav[aria-label="${messages.legalNavigation}"]`)
    expect(navigation.get('a[href="https://www.bbaw.de/datenschutz"]').text()).toBe(
      messages.privacyNotice,
    )
  })

  it('reports unconfigured publication details while retaining licence and legal navigation', async () => {
    const footer = await renderFooter(locale, apiClientWithJsonResponse({}))

    const publication = footer.get('section[aria-labelledby="publication-heading"]')
    expect(publication.text()).toContain(publicationMessages.notConfigured)
    expect(publication.find('dl').exists()).toBe(false)
    expect(footer.findAll('.app-footer-fact')).toHaveLength(1) // licence only
    expect(
      footer.find(`nav[aria-label="${messages.legalNavigation}"] a[href^="mailto:"]`).exists(),
    ).toBe(false)
  })

  it('waits for a successful response before reporting unconfigured publication details', async () => {
    let resolveResponse!: (response: Response) => void
    const response = new Promise<Response>((resolve) => {
      resolveResponse = resolve
    })
    const footer = await renderFooter(locale, createApiClient({ fetch: () => response }))
    const publication = footer.get('section[aria-labelledby="publication-heading"]')

    expect(publication.text()).not.toContain(publicationMessages.notConfigured)
    expect(publication.find('[role="alert"]').exists()).toBe(false)

    resolveResponse(new Response('{}', { headers: { 'content-type': 'application/json' } }))
    await flushPromises()

    expect(publication.text()).toContain(publicationMessages.notConfigured)
  })

  it('distinguishes failed publication details from unconfigured details and retains legal links', async () => {
    const footer = await renderFooter(locale, apiClientWithNetworkError())

    const publication = footer.get('section[aria-labelledby="publication-heading"]')
    expect(publication.get('[role="alert"]').text()).toBe(publicationMessages.loadError)
    expect(publication.text()).not.toContain(publicationMessages.notConfigured)
    expect(publication.find('dl').exists()).toBe(false)
    expect(footer.findAll('.app-footer-fact')).toHaveLength(1)
    expect(footer.get('a[href="/impressum"]')).toBeTruthy()
  })
})
