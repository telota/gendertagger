import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient, type ApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import { SOURCE_CODE_LICENSE } from '@/app/publication'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithJsonResponse, apiClientWithNetworkError } from '../helpers/api'

function apiClientFailingOnce(recoveredBody: unknown): ApiClient {
  let callCount = 0
  return createApiClient({
    fetch: () => {
      callCount += 1
      if (callCount === 1) return Promise.reject(new TypeError('fetch failed'))
      return Promise.resolve(
        new Response(JSON.stringify(recoveredBody), {
          headers: { 'content-type': 'application/json' },
        }),
      )
    },
  })
}
import { mountApplicationAt } from '../helpers/render'

const catalogues = { de, en } as const

const FULL_LEGAL_ENTITY = {
  name: 'Berlin-Brandenburgische Akademie der Wissenschaften',
  legal_form: 'Rechtsfähige Körperschaft des öffentlichen Rechts',
  address_lines: ['Jägerstraße 22/23', '10117 Berlin'],
  telephone: '+49 (0)30 20370-0',
  telephone_href: 'tel:+493020370-0',
  representative: 'Prof. Dr. Dr. h. c. mult. Christoph Markschies',
  vat_id: 'DE 167 449 058',
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('legal notice in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].legal

  it('is titled and organised into labelled sections', async () => {
    const page = (
      await mountApplicationAt('/impressum', locale, apiClientWithJsonResponse({}))
    ).get('main')

    expect(page.get('h1').text()).toBe(messages.title)
    const headings = page.findAll('h2').map((heading) => heading.text())
    expect(headings).toEqual([
      messages.provider.heading,
      messages.responsibility.heading,
      messages.copyright.heading,
      messages.liability.heading,
      messages.privacy.heading,
    ])
    for (const section of page.findAll('section')) {
      expect(section.attributes('aria-labelledby')).toBeTruthy()
    }
  })

  it('shows a loading state before the response arrives', async () => {
    const pending = new Promise<Response>(() => {
      /* never resolves within this test */
    })
    const client = { GET: () => pending } as never
    const page = (await mountApplicationAt('/impressum', locale, client)).get('main')

    const status = page.get('[role="status"]')
    expect(status.text()).toBe(messages.loading)
    expect(status.attributes('aria-atomic')).toBe('true')
    expect(page.find('section').exists()).toBe(false)
  })

  it('shows every configured provider detail', async () => {
    const page = (
      await mountApplicationAt(
        '/impressum',
        locale,
        apiClientWithJsonResponse({ legal_entity: FULL_LEGAL_ENTITY }),
      )
    ).get('main')

    expect(page.text()).toContain(FULL_LEGAL_ENTITY.name)
    expect(page.text()).toContain(FULL_LEGAL_ENTITY.legal_form)
    expect(page.get('address').text()).toContain(FULL_LEGAL_ENTITY.address_lines[0])
    expect(page.get('address').text()).toContain(FULL_LEGAL_ENTITY.address_lines[1])
    expect(page.get(`a[href="${FULL_LEGAL_ENTITY.telephone_href}"]`).text()).toBe(
      FULL_LEGAL_ENTITY.telephone,
    )
    expect(page.text()).toContain(FULL_LEGAL_ENTITY.representative)
    expect(page.text()).toContain(FULL_LEGAL_ENTITY.vat_id)
  })

  it('states each unconfigured section explicitly rather than inventing content', async () => {
    const page = (
      await mountApplicationAt('/impressum', locale, apiClientWithJsonResponse({}))
    ).get('main')

    const notConfigured = page.findAll('.legal-not-configured')
    // provider, responsibility, and privacy each have nothing configured in this fixture.
    expect(notConfigured.length).toBeGreaterThanOrEqual(3)
    for (const paragraph of notConfigured) expect(paragraph.text()).toBe(messages.notConfigured)
  })

  it('names the responsible institution and a contact address when configured', async () => {
    const page = (
      await mountApplicationAt(
        '/impressum',
        locale,
        apiClientWithJsonResponse({
          institution_name: 'TELOTA',
          contact_email: 'telota@bbaw.de',
        }),
      )
    ).get('main')

    expect(page.text()).toContain(messages.responsibility.operator.replace('{operator}', 'TELOTA'))
    expect(page.get('a[href="mailto:telota@bbaw.de"]').text()).toBe('telota@bbaw.de')
  })

  it('always states the source-code licence with its year and holder, and links its text', async () => {
    const page = (
      await mountApplicationAt('/impressum', locale, apiClientWithJsonResponse({}))
    ).get('main')

    expect(page.text()).toContain(SOURCE_CODE_LICENSE.name)
    expect(page.text()).toContain(`© ${SOURCE_CODE_LICENSE.copyrightYear}`)
    expect(page.text()).toContain(SOURCE_CODE_LICENSE.copyrightHolder)
    expect(page.get(`a[href="${SOURCE_CODE_LICENSE.url}"]`).text()).toBe(
      messages.copyright.licenseText,
    )
  })

  it('always warns that machine annotations need editorial review', async () => {
    const page = (
      await mountApplicationAt('/impressum', locale, apiClientWithJsonResponse({}))
    ).get('main')

    expect(page.text()).toContain(messages.liability.machineAnnotations)
  })

  it('links the configured privacy notice', async () => {
    const page = (
      await mountApplicationAt(
        '/impressum',
        locale,
        apiClientWithJsonResponse({ privacy_notice_url: 'https://www.bbaw.de/datenschutz' }),
      )
    ).get('main')

    expect(page.get('a[href="https://www.bbaw.de/datenschutz"]').text()).toBe(messages.privacy.link)
  })

  it('shows an error state with a retry affordance on a fetch failure', async () => {
    const page = (await mountApplicationAt('/impressum', locale, apiClientWithNetworkError())).get(
      'main',
    )

    const alert = page.get('[role="alert"]')
    expect(alert.text()).toBe(messages.loadError)
    expect(alert.attributes('aria-atomic')).toBe('true')
    expect(alert.find('button').exists()).toBe(false)
    expect(page.get('.legal-error').classes()).toContain('app-feedback--critical')
    expect(page.get('.legal-retry').text()).toBe(messages.retry)
    expect(page.find('section').exists()).toBe(false)
  })

  it('recovers from an error once the retry button succeeds', async () => {
    const page = (
      await mountApplicationAt(
        '/impressum',
        locale,
        apiClientFailingOnce({ legal_entity: FULL_LEGAL_ENTITY }),
      )
    ).get('main')
    expect(page.get('[role="alert"]').text()).toBe(messages.loadError)

    await page.get('.legal-retry').trigger('click')
    await flushPromises()

    expect(page.find('[role="alert"]').exists()).toBe(false)
    expect(page.find('.legal-retry').exists()).toBe(false)
    expect(page.text()).toContain(FULL_LEGAL_ENTITY.name)
  })
})
