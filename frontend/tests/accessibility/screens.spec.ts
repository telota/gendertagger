import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AppLocale } from '@/app/i18n'

import { newServer } from '../features/review/fixtures'
import { expectNoAxeViolations } from '../helpers/axe'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'
import { applicationClient, SCREENS } from './mockApi'

/**
 * The whole application, screen by screen, in both locales: exactly one page title, and no axe-core
 * violation. Colour contrast is not computed by jsdom and is asserted against the tokens themselves
 * (tests/styles/tokens.spec.ts); focus behaviour and screen-reader announcements are tested where the
 * interaction is (review, decision, bulk). Real assistive technology remains the manual pass of D17.
 */

// The marker that says a screen has finished loading its data (not just its shell).
const READY: Record<keyof typeof SCREENS, string> = {
  projects: '.project-card, .project-list-item, main li',
  overview: '.snapshot',
  import: '#import-file',
  runs: '.run',
  run: '.execution',
  aggregation: '.aggregation-detail-hash',
  review: '.detail-table',
  people: '.record',
  evaluations: '.evaluation',
  evaluation: '#ensemble-heading',
  exports: '.export',
  export: '.export-detail-download',
}

beforeEach(() => {
  // The run screen opens an event stream; jsdom has no EventSource.
  vi.stubGlobal(
    'EventSource',
    class {
      static readonly CLOSED = 2
      readyState = 0
      addEventListener(): void {}
      close(): void {}
    },
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('accessibility of every screen in %s', (locale: AppLocale) => {
  it.each(Object.entries(SCREENS) as [keyof typeof SCREENS, string][])(
    '%s has one page title and no axe violations',
    async (name, path) => {
      const wrapper = await mountApplicationAt(path, locale, applicationClient())
      await waitFor(() => expect(wrapper.find(READY[name]).exists()).toBe(true), 8000)
      await flushPromises()

      expect(wrapper.findAll('h1')).toHaveLength(1)
      await expectNoAxeViolations(wrapper.element)
    },
  )

  it('the review screen stays free of violations with a decision chosen, the bulk form and its confirmation open', async () => {
    const wrapper = await mountApplicationAt(SCREENS.review, locale, applicationClient())
    await waitFor(() => expect(wrapper.find('.detail-table').exists()).toBe(true), 8000)
    await flushPromises()

    await wrapper.get('#decision-correct-female').setValue(true)
    await wrapper.findAll('.row-check')[0]?.setValue(true)
    await wrapper.findAll('.row-check')[1]?.setValue(true)
    await wrapper.get('#bulk-action').setValue('defer')
    await expectNoAxeViolations(wrapper.element)

    await wrapper.get('.bulk-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.bulk-confirm').exists()).toBe(true))
    await expectNoAxeViolations(wrapper.element)
  })

  it('the review screen stays free of violations when a decision meets a conflict and after a bulk report', async () => {
    const server = newServer({ postOutcome: 'conflict' })
    const wrapper = await mountApplicationAt(SCREENS.review, locale, applicationClient(server))
    await waitFor(() => expect(wrapper.find('.detail-table').exists()).toBe(true), 8000)
    await flushPromises()

    await wrapper.get('#decision-defer').setValue(true)
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.decision-conflict').exists()).toBe(true))
    await expectNoAxeViolations(wrapper.element)

    server.postOutcome = 'ok'
    await wrapper.get('.decision-discard').trigger('click')
    await wrapper.findAll('.row-check')[0]?.setValue(true)
    await wrapper.get('#bulk-action').setValue('defer')
    await wrapper.get('.bulk-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.bulk-apply').exists()).toBe(true))
    await wrapper.get('.bulk-apply').trigger('click')
    await waitFor(() => expect(wrapper.find('.bulk-report').exists()).toBe(true))
    await expectNoAxeViolations(wrapper.element)
  })

  it('the viewer’s read-only variants of the screens are free of violations too', async () => {
    for (const path of [SCREENS.review, SCREENS.runs, SCREENS.evaluations, SCREENS.exports]) {
      const wrapper = await mountApplicationAt(
        path,
        locale,
        applicationClient(newServer({ role: 'viewer' })),
      )
      await waitFor(() => expect(wrapper.find('h1').exists()).toBe(true), 8000)
      await flushPromises()
      await expectNoAxeViolations(wrapper.element)
      wrapper.unmount()
    }
  })
})
