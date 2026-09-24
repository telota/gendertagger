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

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

describe.each(['de', 'en'] as const)('review workbench in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].review
  const base = `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/review`

  async function mountReview(server: Server, query = '') {
    const wrapper = await mountApplicationAt(`${base}${query}`, locale, reviewClient(server))
    await waitFor(() => expect(wrapper.find('.review-grid').exists()).toBe(true))
    await waitFor(() => expect(wrapper.find('.row').exists()).toBe(true))
    await flushPromises()
    return wrapper
  }

  // The list is requested with a page size of 50; a lookup of one person (limit 20) is not the list.
  const last = (server: Server): URLSearchParams => {
    const request = server.requests.filter((r) => r.get('limit') === '50').at(-1)
    if (!request) throw new Error('no review-items request was made')
    return request
  }

  it('keeps a filter token and its gloss apart as words, on screen and for a screen reader', async () => {
    const wrapper = await mountReview(newServer())

    const label = wrapper.get('label[for="review-state-unreviewed"]').text()
    expect(label).toBe(`unreviewed ${messages.gloss.workflow.unreviewed}`)
    expect(wrapper.get('label[for="review-agreement-unanimous"]').text()).toBe(
      `unanimous ${messages.gloss.agreement.unanimous}`,
    )
  })

  it('starts on the contested-evidence queue with its own tiers and the triage order', async () => {
    const server = newServer()
    await mountReview(server)

    expect(server.requests[0]?.getAll('certainty_tiers')).toEqual(['low', 'contested'])
    expect(server.requests[0]?.get('sort')).toBe('uncertainty')
    expect(server.requests[0]?.get('aggregation_id')).toBe(AGG_ID)
  })

  it('shows the queue counts from the summary, not from the loaded page', async () => {
    const wrapper = await mountReview(newServer())

    const counts = wrapper.findAll('.queue-count').map((c) => c.text())
    expect(counts[0]).toMatch(/2.*3/) // contested: 2 open of 3 (low 2 + contested 1)
    expect(counts[1]).toMatch(/2.*2/) // thin: 2 open of 2
    expect(counts[2]).toMatch(/8.*9/) // all: 8 open of 9
  })

  it('keeps the two evidence queues apart and reads the register in TEI order for all', async () => {
    const server = newServer()
    const wrapper = await mountReview(server)

    await wrapper.findAll('.queue')[1]?.trigger('click')
    await waitFor(() =>
      expect(last(server).getAll('certainty_tiers')).toEqual(['single', 'uncertain']),
    )
    expect(last(server).get('sort')).toBe('uncertainty')

    await wrapper.findAll('.queue')[2]?.trigger('click')
    await waitFor(() => expect(last(server).getAll('certainty_tiers')).toEqual([]))
    expect(last(server).get('sort')).toBe('tei_id')
  })

  it('sends every filter to the server, and a method refinement only with its method', async () => {
    const server = newServer()
    const wrapper = await mountReview(server)
    expect(wrapper.find('#review-method-label').exists()).toBe(false)

    await wrapper.get('#review-state-unreviewed').setValue(true)
    await waitFor(() => expect(last(server).getAll('workflow_states')).toEqual(['unreviewed']))
    await wrapper.get('#review-label').setValue('female')
    await waitFor(() => expect(last(server).get('final_label')).toBe('female'))
    await wrapper.get('#review-agreement-no_consensus').setValue(true)
    await waitFor(() => expect(last(server).getAll('agreement_tiers')).toEqual(['no_consensus']))
    await wrapper.get('#review-conflict').setValue('yes')
    await waitFor(() => expect(last(server).get('has_authority_conflict')).toBe('true'))
    await wrapper.get('#review-method').setValue('gnd')
    await waitFor(() => expect(last(server).get('method_name')).toBe('gnd'))
    expect(last(server).get('method_label')).toBeNull()
    await wrapper.get('#review-method-label').setValue('female')
    await wrapper.get('#review-method-status').setValue('abstain')
    await waitFor(() => expect(last(server).get('prediction_status')).toBe('abstain'))
    expect(last(server).get('method_label')).toBe('female')

    await wrapper.get('#review-method').setValue('')
    await waitFor(() => expect(last(server).get('method_name')).toBeNull())
    expect(last(server).get('method_label')).toBeNull()
    expect(last(server).get('prediction_status')).toBeNull()
  })

  it('searches on the server once typing pauses', async () => {
    const server = newServer()
    const wrapper = await mountReview(server)
    const before = server.requests.length

    await wrapper.get('#review-q').setValue('Okaf')
    expect(server.requests.length).toBe(before)
    await waitFor(() => expect(last(server).get('q')).toBe('Okaf'))
  })

  it('continues with the cursor and only within the same filter tuple', async () => {
    const server = newServer({
      pages: [
        { items: [item('demo-1')], next: '1' },
        { items: [item('demo-2')], next: null },
      ],
    })
    const wrapper = await mountReview(server)

    await wrapper.get('.review-list-more').trigger('click')
    await waitFor(() => expect(wrapper.findAll('.row')).toHaveLength(2))

    expect(last(server).get('cursor')).toBe('1')
    expect(last(server).getAll('certainty_tiers')).toEqual(['low', 'contested'])
    expect(wrapper.find('.review-list-more').exists()).toBe(false)
  })

  it('opens the first entry and shows tokens untranslated beside a plain-language gloss', async () => {
    const wrapper = await mountReview(newServer())
    await waitFor(() => expect(wrapper.find('.detail').exists()).toBe(true))

    const facts = wrapper.get('.detail-facts').text()
    expect(facts).toContain('contested')
    expect(facts).toContain(messages.gloss.certainty.contested)
    expect(facts).toContain('no_consensus')
    expect(wrapper.get('.row[aria-current="true"]').text()).toContain('Surname-demo-1')
  })

  it('says when an authority overruled the vote', async () => {
    const wrapper = await mountReview(newServer())
    await waitFor(() => expect(wrapper.find('.detail-authority').exists()).toBe(true))

    expect(wrapper.get('.detail-authority').text()).toContain(messages.detail.authorityTitle)
    expect(wrapper.get('.detail-authority').text()).toContain(messages.gloss.override.gnd)
  })

  it('keeps abstain, error, a stored unknown and a missing prediction apart, and calls confidence method-specific', async () => {
    const wrapper = await mountReview(newServer())
    await waitFor(() => expect(wrapper.find('.detail-table').exists()).toBe(true))

    const rows = wrapper.findAll('.detail-table tbody tr').map((row) => row.text())
    expect(rows[0]).toContain('gnd')
    expect(rows[1]).toContain('error')
    expect(rows[2]).toContain('abstain')
    expect(rows[3]).toContain('unknown')
    expect(rows[3]).toMatch(/0[.,]42/)
    expect(rows[4]).toContain(messages.detail.methods.noPrediction)
    expect(wrapper.get('.detail-note').text()).toBe(messages.detail.methods.confidenceNote)
    // Nothing but the one method that reported a confidence shows a number.
    expect(rows.filter((row) => /\d[.,]\d/.test(row))).toHaveLength(1)
  })

  it('reads out the annotation chain with names, newest first', async () => {
    const wrapper = await mountReview(newServer())
    await waitFor(() => expect(wrapper.find('.detail-history').exists()).toBe(true))

    const entries = wrapper.findAll('.detail-history-entry').map((entry) => entry.text())
    expect(entries[0]).toContain('correct')
    expect(entries[0]).toContain('Jo Reviewer')
    expect(entries[0]).toContain('Attested as a woman.')
    expect(entries[1]).toContain('defer')
    expect(entries[1]).toContain('Sam Reviewer')
  })

  it('reaches a person the list does not hold through a deep link', async () => {
    const server = newServer({
      pages: [{ items: [item('demo-1')], next: null }],
      known: [item('demo-9', { surname: 'Deeplinked' })],
    })
    const wrapper = await mountReview(server, '?person=demo-9')
    await waitFor(() => expect(wrapper.find('.detail-name').exists()).toBe(true))

    expect(wrapper.get('.detail-name').text()).toContain('Deeplinked')
  })

  it('says so instead of showing an empty queue while the aggregation has not finished', async () => {
    const server = newServer({ aggregationStatus: 'running' })
    const wrapper = await mountApplicationAt(base, locale, reviewClient(server))
    await waitFor(() => expect(wrapper.find('.review-not-ready').exists()).toBe(true))
    await wait(30)

    expect(wrapper.get('.review-not-ready').text()).toBe(messages.notCompleted)
    expect(wrapper.find('.review-grid').exists()).toBe(false)
    expect(server.requests).toHaveLength(0)
  })

  it('moves between rows with the arrow keys', async () => {
    const wrapper = await mountReview(newServer())
    const rows = wrapper.findAll('button.row')
    ;(rows[0]?.element as HTMLButtonElement).focus()

    await rows[0]?.trigger('keydown', { key: 'ArrowDown' })

    expect(document.activeElement).toBe(rows[1]?.element)
  })
})
