import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import App from '@/app/App.vue'
import { createAppI18n, type AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../helpers/axe'

const catalogues = { de, en } as const

function render(locale: AppLocale) {
  return mount(App, {
    attachTo: document.body,
    global: { plugins: [createAppI18n(locale)] },
  })
}

afterEach(() => {
  document.body.replaceChildren()
  delete document.documentElement.dataset.theme
})

describe.each(['de', 'en'] as const)('App in %s', (locale) => {
  it('renders one page title and the notice from the catalogue', () => {
    const wrapper = render(locale)

    expect(wrapper.get('h1').text()).toBe(catalogues[locale].app.title)
    expect(wrapper.get('main').text()).toContain(catalogues[locale].app.scaffoldNotice)
  })

  it.each(['light', 'dark'] as const)('has no axe violations in the %s theme', async (theme) => {
    document.documentElement.dataset.theme = theme
    const wrapper = render(locale)

    await expectNoAxeViolations(wrapper.element)
  })
})
