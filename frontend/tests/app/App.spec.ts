import { afterEach, describe, expect, it } from 'vitest'

import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithJsonResponse } from '../helpers/api'
import { expectNoAxeViolations } from '../helpers/axe'
import { mountApplicationAt } from '../helpers/render'

const catalogues = { de, en } as const
const PAGES = ['/', '/login', '/impressum', '/gibt-es-nicht'] as const

afterEach(() => {
  document.body.replaceChildren()
  delete document.documentElement.dataset.theme
})

describe.each(['de', 'en'] as const)('application shell in %s', (locale) => {
  it('renders the start page with its application title', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithJsonResponse({}))

    expect(wrapper.get('h1').text()).toBe(catalogues[locale].app.title)
  })

  it.each(PAGES)('shows publication details once in the footer on %s', async (path) => {
    const wrapper = await mountApplicationAt(path, locale, apiClientWithJsonResponse({}))

    const footer = wrapper.get('.app-footer')
    const publication = footer.get('section[aria-labelledby="publication-heading"]')
    expect(publication.get('h2#publication-heading').text()).toBe(
      catalogues[locale].publication.heading,
    )
    expect(wrapper.findAll('#publication-heading')).toHaveLength(1)
    expect(wrapper.get('main').text()).not.toContain(catalogues[locale].publication.heading)
    expect(footer.text()).toContain(catalogues[locale].footer.legalNotice)
  })

  it.each(PAGES)('has one page title and no axe violations on %s', async (path) => {
    for (const theme of ['light', 'dark'] as const) {
      document.documentElement.dataset.theme = theme
      const wrapper = await mountApplicationAt(path, locale, apiClientWithJsonResponse({}))

      expect(wrapper.findAll('h1')).toHaveLength(1)
      await expectNoAxeViolations(wrapper.element)
      wrapper.unmount()
    }
  })
})
