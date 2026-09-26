import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

const catalogues = { de, en } as const
const USER = { id: 'a0000000-0000-0000-0000-000000000002', display_name: 'Viewer', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
const RUN_ID = 'd0000000-0000-0000-0000-000000000001'
const EXECUTION_ID = 'e0000000-0000-0000-0000-000000000001'
const RESULTS_PATH = '/api/v1/runs/' + RUN_ID + '/executions/' + EXECUTION_ID + '/results'

function progress(completed: number, failed: number, total: number) {
  return {
    completed,
    failed,
    total,
    percentage: Math.round(((completed + failed) / total) * 100),
  }
}

function run() {
  return {
    id: RUN_ID,
    dataset_snapshot_id: SNAPSHOT_ID,
    status: 'completed_with_errors',
    created_at: '2026-01-01T10:00:00Z',
    finished_at: '2026-01-01T10:01:00Z',
    config_sha256: 'e'.repeat(64),
    resolved_config: { methods: [] },
    progress: progress(69, 1, 70),
    application_version: '1',
    code_git_commit: 'abc',
    python_version: '3.12',
  }
}

function execution(status = 'completed') {
  return {
    id: EXECUTION_ID,
    run_id: RUN_ID,
    method_name: 'gender_guesser',
    status,
    progress: progress(69, 1, 70),
    completed_count: 69,
    failed_count: 1,
    total_count: 70,
    implementation_version: 'v1',
    normalization_version: 'v1',
    config_sha256: 'f'.repeat(64),
    resolved_config: {},
    created_at: '2026-01-01T10:00:00Z',
    finished_at: '2026-01-01T10:01:00Z',
  }
}

const item = (
  id: string,
  state: 'missing' | 'success' | 'abstain' | 'error',
  prediction: Record<string, unknown> | null,
  forenames: string[] | null = ['Ada'],
) => ({
  method_execution_id: EXECUTION_ID,
  dataset_snapshot_id: SNAPSHOT_ID,
  person_record_id: id,
  tei_id: 'person-' + id,
  surname: 'Example',
  ...(forenames === null ? {} : { forenames }),
  result_state: state,
  prediction_id: prediction === null ? null : 'prediction-' + id,
  prediction,
})

const firstPage = {
  items: [
    item('1', 'success', {
      label: 'unknown',
      status: 'success',
      method_confidence: 0.75,
      raw_label: 'u',
    }),
    item('2', 'missing', null, null),
    item('3', 'abstain', {
      label: null,
      status: 'abstain',
      method_confidence: null,
      raw_label: null,
    }),
    item('4', 'error', {
      label: null,
      status: 'error',
      method_confidence: null,
      raw_label: null,
    }),
  ],
  next_cursor: 'second-page',
  has_more: true,
}
const secondPage = {
  items: [
    item('5', 'success', {
      label: 'female',
      status: 'success',
      method_confidence: 0.95,
      raw_label: 'female',
    }),
  ],
  next_cursor: null,
  has_more: false,
}

interface Server {
  resultRequests: URL[]
  requests: URL[]
  executionStatus?: string
}

function client(server: Server) {
  return createApiClient({
    fetch: async (request) => {
      const url = new URL(request.url)
      server.requests.push(url)
      if (url.pathname === '/api/v1/branding') return jsonResponse({})
      if (url.pathname === '/api/v1/me') return jsonResponse(USER)
      if (url.pathname === '/api/v1/auth/session') {
        return jsonResponse({ must_change_password: false, keep_signed_in: false })
      }
      if (url.pathname === '/api/v1/projects/' + PROJECT_ID) {
        return jsonResponse({
          id: PROJECT_ID,
          slug: 'p',
          display_name: 'Project A',
          current_user_role: 'viewer',
        })
      }
      if (url.pathname === '/api/v1/snapshots/' + SNAPSHOT_ID) {
        return jsonResponse({
          id: SNAPSHOT_ID,
          project_id: PROJECT_ID,
          status: 'ready',
          created_at: '2026-01-01T09:00:00Z',
        })
      }
      if (url.pathname === '/api/v1/runs/' + RUN_ID) return jsonResponse(run())
      if (url.pathname === '/api/v1/runs/' + RUN_ID + '/executions') {
        return jsonResponse([execution(server.executionStatus)])
      }
      if (url.pathname === RESULTS_PATH) {
        server.resultRequests.push(url)
        return jsonResponse(url.searchParams.get('cursor') ? secondPage : firstPage)
      }
      return jsonResponse({}, { status: 404 })
    },
  })
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('method results in %s', (locale: AppLocale) => {
  const messages = catalogues[locale]
  const page =
    '/projects/' +
    PROJECT_ID +
    '/snapshots/' +
    SNAPSHOT_ID +
    '/runs/' +
    RUN_ID +
    '/executions/' +
    EXECUTION_ID +
    '/results'

  it('does not request results for an execution outside the run', async () => {
    const server: Server = { resultRequests: [], requests: [] }
    const invalidPage = page.replace(EXECUTION_ID, 'e0000000-0000-0000-0000-000000000099')
    const wrapper = await mountApplicationAt(invalidPage, locale, client(server))

    await waitFor(() => expect(wrapper.text()).toContain(messages.runs.contextUnavailable))
    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(server.resultRequests).toHaveLength(0)
  })

  it('does not request a changing collection for a method that is still running', async () => {
    const server: Server = {
      resultRequests: [],
      requests: [],
      executionStatus: 'running',
    }
    const wrapper = await mountApplicationAt(page, locale, client(server))

    await waitFor(() => expect(wrapper.text()).toContain(messages.runs.results.notFinal))
    expect(server.resultRequests).toHaveLength(0)
  })

  it('lists raw method decisions independently from aggregation and preserves every result state', async () => {
    const server: Server = { resultRequests: [], requests: [] }
    const wrapper = await mountApplicationAt(page, locale, client(server))

    await waitFor(() => expect(wrapper.findAll('.method-results-table tbody tr')).toHaveLength(4))
    expect(wrapper.get('h1').text()).toBe(messages.runs.results.title)
    expect(wrapper.get('.method-results-heading').text()).toContain('gender_guesser')
    expect(wrapper.text()).toContain('unknown')
    expect(wrapper.text()).toContain('missing')
    expect(wrapper.text()).toContain('abstain')
    expect(wrapper.text()).toContain('error')
    expect(wrapper.text()).toContain(messages.runs.results.noPrediction)
    expect(wrapper.text()).toContain(messages.runs.results.confidenceNote)
    expect(wrapper.get('.method-results-back').attributes('href')).toBe(
      '/projects/' + PROJECT_ID + '/snapshots/' + SNAPSHOT_ID + '/runs/' + RUN_ID,
    )
    expect(server.resultRequests).toHaveLength(1)
    expect(server.requests.some((request) => request.pathname.includes('/aggregations'))).toBe(
      false,
    )
    await expectNoAxeViolations(wrapper.element)

    await wrapper.get('.method-results .app-button').trigger('click')
    await waitFor(() => expect(wrapper.findAll('.method-results-table tbody tr')).toHaveLength(5))
    expect(server.resultRequests).toHaveLength(2)
  })
})
