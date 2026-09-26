import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'

import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'
import {
  AGG_ID,
  catalogues,
  item,
  newServer,
  PROJECT_ID,
  reviewClient,
  RUN_ID,
  type Server,
} from './fixtures'

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('person browser in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].review
  const people = `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/people`

  async function mountPeople(server: Server, query = '') {
    const wrapper = await mountApplicationAt(`${people}${query}`, locale, reviewClient(server))
    await waitFor(() => expect(wrapper.find('.row').exists()).toBe(true))
    await flushPromises()
    return wrapper
  }

  const last = (server: Server): URLSearchParams => {
    const request = server.requests.filter((r) => r.get('limit') === '50').at(-1)
    if (!request) throw new Error('no review-items request was made')
    return request
  }

  it('lists the whole register in TEI order, whatever the automation made of it', async () => {
    const server = newServer({
      pages: [
        {
          items: [
            item('demo-1', { certainty_tier: 'high', agreement_tier: 'unanimous' }),
            item('demo-2', { certainty_tier: 'no_data', machine_label: null, final_label: null }),
          ],
          next: null,
        },
      ],
    })
    const wrapper = await mountPeople(server)

    expect(wrapper.get('.review-title').text()).toBe(messages.people.title)
    expect(wrapper.find('.queues').exists()).toBe(false)
    expect(server.requests[0]?.getAll('certainty_tiers')).toEqual([])
    expect(server.requests[0]?.get('sort')).toBe('tei_id')
    expect(wrapper.findAll('.row')).toHaveLength(2)
  })

  it('offers the register filters only: search, order, review state and final label', async () => {
    const wrapper = await mountPeople(newServer())

    expect(wrapper.find('#review-q').exists()).toBe(true)
    expect(wrapper.find('#review-sort').exists()).toBe(true)
    expect(wrapper.find('#review-state-unreviewed').exists()).toBe(true)
    expect(wrapper.find('#review-label').exists()).toBe(true)
    expect(wrapper.find('#review-agreement-no_consensus').exists()).toBe(false)
    expect(wrapper.find('#review-conflict').exists()).toBe(false)
    expect(wrapper.find('#review-method').exists()).toBe(false)
  })

  it('returns a read-only viewer to available project data when changing the selection', async () => {
    const wrapper = await mountPeople(newServer({ role: 'viewer' }))
    try {
      expect(wrapper.get('.review-heading-row a').attributes('href')).toBe(
        `/projects/${PROJECT_ID}/snapshots`,
      )
    } finally {
      wrapper.unmount()
    }
  })

  it('finds a person by an authority id, other name or TEI id, all through the server search', async () => {
    const server = newServer()
    const wrapper = await mountPeople(server)

    await wrapper.get('#review-q').setValue('118607626')
    await waitFor(() => expect(last(server).get('q')).toBe('118607626'))
    expect(last(server).getAll('certainty_tiers')).toEqual([])
    expect(wrapper.get('label[for="review-q"]').text()).toBe(messages.filters.search)
  })

  it('reaches a person through a deep link, and keeps the register filters in the address', async () => {
    const server = newServer({
      pages: [{ items: [item('demo-1')], next: null }],
      known: [item('demo-9', { surname: 'Deeplinked' })],
    })
    const wrapper = await mountPeople(server, '?person=demo-9&label=female')
    await waitFor(() => expect(wrapper.find('.detail-name').exists()).toBe(true))

    expect(wrapper.get('.detail-name').text()).toContain('Deeplinked')
    expect(last(server).get('final_label')).toBe('female')
  })

  it('shows every source-preserving field of the register entry', async () => {
    const wrapper = await mountPeople(newServer())
    await waitFor(() => expect(wrapper.find('.record').exists()).toBe(true))

    const forms = wrapper.findAll('.record-name-form').map((li) => li.text())
    expect(forms[0]).toContain('reg')
    expect(forms[1]).toContain('alt')
    expect(forms[1]).toContain('birthname')
    expect(forms[1]).toContain('Gottfried Sturm')

    const events = wrapper.findAll('.record-event').map((li) => li.text())
    expect(events[0]).toContain('wedding')
    expect(events[0]).toContain('1817-09-24')
    expect(events[0]).toContain('Berlin')
    expect(events[1]).toContain('appointment')

    const ids = wrapper.findAll('.record-external-id').map((li) => li.text())
    expect(ids.join(' ')).toContain('viaf')
    expect(ids.join(' ')).toContain('Q42')

    expect(wrapper.get('.record-source').text()).toBe(
      messages.detail.person.source.replace('{file}', 'persons-a.xml').replace('{locator}', '17'),
    )
    expect(wrapper.get('.record').text()).toContain('Fritz S.')
  })

  it('shows the whole chain of decisions with who, when, which revision and what it replaced', async () => {
    const wrapper = await mountPeople(newServer())
    await waitFor(() => expect(wrapper.find('.detail-history').exists()).toBe(true))

    const entries = wrapper.findAll('.detail-history-entry')
    expect(entries).toHaveLength(2)

    // Newest first: the current decision replaces the one below it.
    expect(entries[0]?.text()).toContain('Jo Reviewer')
    expect(entries[0]?.text()).toContain(messages.detail.history.current)
    expect(entries[0]?.text()).toContain(
      messages.detail.history.replaces.replace('{revision}', '1'),
    )
    expect(entries[0]?.text()).toContain(messages.detail.history.entry.replace('{revision}', '2'))
    expect(entries[0]?.text()).toContain('Attested as a woman.')

    // The oldest has nothing to replace and is not the current one.
    expect(entries[1]?.text()).toContain('Sam Reviewer')
    expect(entries[1]?.text()).not.toContain(messages.detail.history.current)
    expect(entries[1]?.text()).not.toMatch(/replaces|ersetzt/)
    // Both carry a readable date.
    expect(entries[0]?.text()).toMatch(/2026|Jan/)
  })

  it('links the review context to the aggregation it belongs to', async () => {
    const wrapper = await mountPeople(newServer())

    expect(wrapper.get('.review-context-link').attributes('href')).toContain(
      `/aggregations/${AGG_ID}`,
    )
  })
})
