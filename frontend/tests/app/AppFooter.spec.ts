import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { ApiClient } from '@/api'
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

  it('names the configured publisher and links to it', async () => {
    const footer = await renderFooter(
      locale,
      apiClientWithJsonResponse({
        institution_name: 'Berlin-Brandenburgische Akademie der Wissenschaften',
        institution_url: 'https://www.bbaw.de/',
      }),
    )

    const link = footer.get('a[href="https://www.bbaw.de/"]')
    expect(link.text()).toBe('Berlin-Brandenburgische Akademie der Wissenschaften')
    expect(footer.text()).toContain(messages.publisher)
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

    expect(footer.text()).toContain(messages.initiatives)
    expect(footer.get('a[href="https://gender-data.bbaw.de/"]').text()).toBe('Gender & Data')
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

  it('omits every configurable row when nothing is configured', async () => {
    const footer = await renderFooter(locale, apiClientWithJsonResponse({}))

    expect(footer.findAll('.app-footer-fact')).toHaveLength(1) // licence only
    expect(
      footer.find(`nav[aria-label="${messages.legalNavigation}"] a[href^="mailto:"]`).exists(),
    ).toBe(false)
  })

  it('degrades to the licence and legal-notice link alone on a fetch error', async () => {
    const footer = await renderFooter(locale, apiClientWithNetworkError())

    expect(footer.findAll('.app-footer-fact')).toHaveLength(1)
    expect(footer.get('a[href="/impressum"]')).toBeTruthy()
  })
})
