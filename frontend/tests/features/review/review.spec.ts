import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

const catalogues = { de, en } as const
const USER = { id: 'a0000000-0000-0000-0000-000000000002', display_name: 'Op', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
const RUN_ID = 'd0000000-0000-0000-0000-000000000001'
const AGG_ID = 'f0000000-0000-0000-0000-000000000001'

function item(tei: string, extra: Record<string, unknown> = {}) {
  return {
    aggregation_execution_id: AGG_ID,
    aggregated_result_id: `r-${tei}`,
    snapshot_id: SNAPSHOT_ID,
    person_record_id: `p-${tei}`,
    tei_id: tei,
    surname: `Surname-${tei}`,
    forenames: ['Given'],
    aggregation_outcome: 'decided',
    machine_label: 'male',
    final_label: 'male',
    agreement_tier: 'weak_majority',
    certainty_tier: 'low',
    override_source: null,
    has_authority_conflict: false,
    has_prediction_error: false,
    workflow_state: 'unreviewed',
    review_revision: 0,
    current_annotation_id: null,
    selected_method_result: null,
    ...extra,
  }
}

const SUMMARY = {
  aggregation_execution_id: AGG_ID,
  result_count: 9,
  last_annotated_at: null,
  groups: [
    {
      certainty_tier: 'high',
      agreement_tier: 'unanimous',
      workflow_state: 'unreviewed',
      final_label: 'male',
      review_action: null,
      result_count: 4,
    },
    {
      certainty_tier: 'low',
      agreement_tier: 'weak_majority',
      workflow_state: 'unreviewed',
      final_label: 'male',
      review_action: null,
      result_count: 2,
    },
    {
      certainty_tier: 'contested',
      agreement_tier: 'no_consensus',
      workflow_state: 'reviewed',
      final_label: 'female',
      review_action: 'correct',
      result_count: 1,
    },
    {
      certainty_tier: 'single',
      agreement_tier: 'single_rater',
      workflow_state: 'unreviewed',
      final_label: 'institution',
      review_action: null,
      result_count: 2,
    },
  ],
}

const PREDICTIONS = [
  {
    method_execution_id: 'x1',
    method_name: 'gnd',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: 'pr1',
    prediction: {
      label: 'female',
      status: 'success',
      method_confidence: null,
      raw_label: 'f',
      raw_output: {},
      metadata: {},
    },
  },
  {
    method_execution_id: 'x2',
    method_name: 'hf_distilbert',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: 'pr2',
    prediction: {
      label: null,
      status: 'error',
      method_confidence: null,
      raw_label: null,
      raw_output: {},
      metadata: {},
    },
  },
  {
    method_execution_id: 'x3',
    method_name: 'gender_guesser',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: 'pr3',
    prediction: {
      label: null,
      status: 'abstain',
      method_confidence: null,
      raw_label: null,
      raw_output: {},
      metadata: {},
    },
  },
  {
    method_execution_id: 'x4',
    method_name: 'local_llm',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: 'pr4',
    prediction: {
      label: 'unknown',
      status: 'success',
      method_confidence: 0.42,
      raw_label: 'unclear',
      raw_output: {},
      metadata: {},
    },
  },
  {
    method_execution_id: 'x5',
    method_name: 'nomquamgender',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: null,
    prediction: null,
  },
]

const HISTORY = {
  snapshot_id: SNAPSHOT_ID,
  person_record_id: 'p',
  tei_id: 'demo-1',
  revision: 2,
  workflow_state: 'reviewed',
  current_annotation_id: 'a2',
  annotations: [
    {
      id: 'a2',
      snapshot_id: SNAPSHOT_ID,
      person_record_id: 'p',
      tei_id: 'demo-1',
      action: 'correct',
      label: 'female',
      reviewer_user_id: 'u',
      reviewer_display_name: 'Jo Reviewer',
      comment: 'Attested as a woman.',
      aggregated_result_id: 'r',
      supersedes_annotation_id: 'a1',
      resulting_revision: 2,
      created_at: '2026-01-02T10:00:00Z',
    },
    {
      id: 'a1',
      snapshot_id: SNAPSHOT_ID,
      person_record_id: 'p',
      tei_id: 'demo-1',
      action: 'defer',
      label: null,
      reviewer_user_id: 'u2',
      reviewer_display_name: 'Sam Reviewer',
      comment: null,
      aggregated_result_id: 'r',
      supersedes_annotation_id: null,
      resulting_revision: 1,
      created_at: '2026-01-01T10:00:00Z',
    },
  ],
}

interface Server {
  aggregationStatus: string
  /** One entry per request, in order: the query string of `GET /review-items`. */
  requests: URLSearchParams[]
  pages: { items: ReturnType<typeof item>[]; next: string | null }[]
  known: ReturnType<typeof item>[]
}

function newServer(overrides: Partial<Server> = {}): Server {
  return {
    aggregationStatus: 'completed',
    requests: [],
    pages: [
      {
        items: [
          item('demo-1', {
            override_source: 'gnd',
            certainty_tier: 'contested',
            agreement_tier: 'no_consensus',
          }),
          item('demo-2'),
        ],
        next: null,
      },
    ],
    known: [],
    ...overrides,
  }
}

function reviewClient(server: Server) {
  return createApiClient({
    fetch: async (request) => {
      const url = new URL(request.url)
      const { pathname } = url
      if (pathname === '/api/v1/branding') return jsonResponse({})
      if (pathname === '/api/v1/me') return jsonResponse(USER)
      if (pathname === '/api/v1/auth/session') {
        return jsonResponse({ must_change_password: false, keep_signed_in: false })
      }
      if (pathname === '/api/v1/methods') {
        return jsonResponse([
          {
            name: 'gnd',
            implementation_version: 'v1',
            normalization_version: 'v1',
            method_confidence_range: null,
          },
          {
            name: 'local_llm',
            implementation_version: 'v1',
            normalization_version: 'v1',
            method_confidence_range: { minimum: 0, maximum: 1 },
          },
        ])
      }
      if (pathname === `/api/v1/aggregations/${AGG_ID}`) {
        return jsonResponse({
          id: AGG_ID,
          run_id: RUN_ID,
          strategy: 'reference_v1',
          status: server.aggregationStatus,
          resolved_config: {},
          method_execution_ids: [],
          config_sha256: '9'.repeat(64),
          created_at: '2026-01-01T11:00:00Z',
        })
      }
      if (pathname === `/api/v1/aggregations/${AGG_ID}/review-summary`) return jsonResponse(SUMMARY)
      if (pathname === '/api/v1/review-items') {
        server.requests.push(url.searchParams)
        const cursor = url.searchParams.get('cursor')
        const q = url.searchParams.get('q')
        if (q !== null && server.known.length > 0) {
          return jsonResponse({
            items: server.known.filter((i) => i.tei_id === q),
            next_cursor: null,
            has_more: false,
          })
        }
        const index = cursor === null ? 0 : Number(cursor)
        const page = server.pages[index] ?? { items: [], next: null }
        return jsonResponse({
          items: page.items,
          next_cursor: page.next,
          has_more: page.next !== null,
        })
      }
      if (pathname.endsWith('/predictions')) return jsonResponse(PREDICTIONS)
      if (pathname === '/api/v1/annotations') return jsonResponse(HISTORY)
      if (pathname.startsWith(`/api/v1/snapshots/${SNAPSHOT_ID}/people/`)) {
        return jsonResponse({
          id: 'p',
          dataset_snapshot_id: SNAPSHOT_ID,
          tei_id: 'demo-1',
          surname: 'S',
          forenames: ['G'],
          birth: '1768',
          death: '1834',
          gnd_id: '118607626',
          note: 'A theologian.',
          created_at: '2026-01-01T00:00:00Z',
        })
      }
      return jsonResponse({}, { status: 404 })
    },
  })
}

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
