import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient, type components } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore } from '@/stores/session'

import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'
import realReport from './fixtures/seed-report.json'

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
const EVAL_ID = 'e1000000-0000-0000-0000-000000000001'
const NEW_EVAL_ID = 'e1000000-0000-0000-0000-000000000002'
const EXEC = {
  pq: 'x0000000-0000-0000-0000-000000000001',
  gnd: 'x0000000-0000-0000-0000-000000000002',
  gg: 'x0000000-0000-0000-0000-000000000003',
  wiki: 'x0000000-0000-0000-0000-000000000004',
}

const progress = { completed: 7, failed: 0, total: 7, percentage: 100 }
function execution(id: string, method: string) {
  return {
    id,
    run_id: RUN_ID,
    method_name: method,
    status: 'completed',
    progress,
    completed_count: 7,
    failed_count: 0,
    total_count: 7,
    implementation_version: `${method}_v1`,
    normalization_version: `${method}_v1`,
    config_sha256: 'f'.repeat(64),
    resolved_config: {},
    created_at: '2026-01-01T10:00:00Z',
  }
}

function evaluation(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: EVAL_ID,
    run_id: RUN_ID,
    definition: 'gnd_benchmark_v1',
    aggregation_execution_id: AGG_ID,
    config_sha256: '8'.repeat(64),
    resolved_config: { id: 'gnd_benchmark_v1', confidence_level: 0.95 },
    method_execution_ids: [EXEC.gnd, EXEC.gg, EXEC.wiki],
    status,
    report_artifact_id: status === 'completed' ? 'artifact' : null,
    created_at: '2026-01-01T12:00:00Z',
    started_at: '2026-01-01T12:00:01Z',
    finished_at: status === 'completed' ? '2026-01-01T12:00:05Z' : null,
    ...extra,
  }
}

const REPORT = {
  definition: 'gnd_benchmark_v1',
  benchmark: {
    method_name: 'gnd',
    labels: ['male', 'female'],
    size: 7,
    class_counts: { male: 4, female: 3 },
  },
  coverage: [
    {
      method_name: 'gnd',
      total: 7,
      coverage_count: 7,
      coverage_share: 1,
      label_distribution: { male: 4, female: 3, unknown: 0, institution: 0 },
      abstain_count: 0,
      error_count: 0,
    },
    {
      method_name: 'gender_guesser',
      total: 7,
      coverage_count: 5,
      coverage_share: 0.714,
      label_distribution: { male: 3, female: 2, unknown: 0, institution: 0 },
      abstain_count: 1,
      error_count: 1,
    },
    {
      method_name: 'wiki_gendersort',
      total: 7,
      coverage_count: 6,
      coverage_share: 0.857,
      label_distribution: { male: 3, female: 3, unknown: 0, institution: 0 },
      abstain_count: 1,
      error_count: 0,
    },
  ],
  accuracy: [
    {
      method_name: 'gender_guesser',
      answered_count: 5,
      correct_count: 4,
      accuracy: 0.8,
      effective_accuracy: 0.571,
      confusion_matrix: {
        male: { male: 3, female: 0, unknown: 0, institution: 0 },
        female: { male: 1, female: 1, unknown: 0, institution: 0 },
      },
      recall: [
        { label: 'male', class_size: 4, correct: 3, recall: 0.75, ci_low: 0.301, ci_high: 0.954 },
        {
          label: 'female',
          class_size: 3,
          correct: 1,
          recall: 0.333,
          ci_low: 0.061,
          ci_high: 0.792,
        },
      ],
    },
    {
      method_name: 'wiki_gendersort',
      answered_count: 6,
      correct_count: 6,
      accuracy: 1,
      effective_accuracy: 0.857,
      confusion_matrix: {
        male: { male: 3, female: 0, unknown: 0, institution: 0 },
        female: { male: 0, female: 3, unknown: 0, institution: 0 },
      },
      recall: [
        { label: 'male', class_size: 4, correct: 3, recall: 0.75, ci_low: 0.301, ci_high: 0.954 },
        { label: 'female', class_size: 3, correct: 3, recall: 1, ci_low: 0.439, ci_high: 1 },
      ],
    },
  ],
  kappa_matrix: [
    { method_a: 'gender_guesser', method_b: 'wiki_gendersort', co_answered_count: 5, kappa: 0.615 },
    { method_a: 'gender_guesser', method_b: 'hivoto_xgboost', co_answered_count: 1, kappa: null },
    { method_a: 'wiki_gendersort', method_b: 'hivoto_xgboost', co_answered_count: 4, kappa: 0.25 },
  ],
  ensemble: {
    canonical_label_distribution: { male: 3, female: 3, unknown: 0, institution: 1 },
    agreement_tier_distribution: {
      unanimous: 4,
      strong_majority: 1,
      weak_majority: 1,
      no_consensus: 1,
      single_rater: 0,
      no_answer: 0,
    },
    certainty_tier_distribution: {
      high: 5,
      low: 1,
      contested: 1,
      single: 0,
      uncertain: 0,
      no_data: 0,
    },
    human_reviewed_count: 3,
    human_correction_count: 1,
  },
}

interface Server {
  role: 'operator' | 'viewer'
  evaluations: ReturnType<typeof evaluation>[]
  detail: ReturnType<typeof evaluation>
  report: unknown
  createStatus: 202 | 409
  createResponse?: Promise<Response>
  posts: Record<string, unknown>[]
  reportRequests: number
  listFailures: number
  listRequests: number
  nextListResponse?: Promise<Response>
}

function newServer(overrides: Partial<Server> = {}): Server {
  return {
    role: 'operator',
    evaluations: [],
    detail: evaluation('completed'),
    report: REPORT,
    createStatus: 202,
    posts: [],
    reportRequests: 0,
    listFailures: 0,
    listRequests: 0,
    ...overrides,
  }
}

function evaluationClient(server: Server) {
  return createApiClient({
    fetch: async (request) => {
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/branding') return jsonResponse({})
      if (pathname === '/api/v1/me') return jsonResponse(USER)
      if (pathname === '/api/v1/auth/session') {
        return jsonResponse({ must_change_password: false, keep_signed_in: false })
      }
      if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
        return jsonResponse({
          id: PROJECT_ID,
          slug: 'p',
          display_name: 'Project A',
          description: null,
          team: {
            id: 'b1000000-0000-0000-0000-000000000001',
            slug: 'editorial-team',
            display_name: 'Editorial team',
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
          manager_user_id: 'a0000000-0000-0000-0000-000000000003',
          created_by_user_id: 'a0000000-0000-0000-0000-000000000003',
          current_user_role: server.role,
          current_user_can_manage_members: false,
          game_mode_enabled: false,
          created_at: '2026-01-01T00:00:00Z',
        } satisfies components['schemas']['AccessibleProject'])
      }
      if (pathname === `/api/v1/runs/${RUN_ID}`) {
        return jsonResponse({
          id: RUN_ID,
          dataset_snapshot_id: SNAPSHOT_ID,
          status: 'completed',
          created_at: '2026-01-01T10:00:00Z',
          config_sha256: 'e'.repeat(64),
          resolved_config: { methods: [] },
          progress,
          application_version: '1',
          code_git_commit: 'abc',
          python_version: '3.12',
        })
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/executions`) {
        return jsonResponse([
          execution(EXEC.pq, 'parenthetical_qualifier'),
          execution(EXEC.gnd, 'gnd'),
          execution(EXEC.gg, 'gender_guesser'),
          execution(EXEC.wiki, 'wiki_gendersort'),
        ])
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/aggregations`) {
        return jsonResponse({
          items: [
            {
              id: AGG_ID,
              run_id: RUN_ID,
              strategy: 'reference_v1',
              status: 'completed',
              resolved_config: {},
              method_execution_ids: [],
              config_sha256: '9'.repeat(64),
              created_at: '2026-01-01T11:00:00Z',
            },
          ],
          next_cursor: null,
          has_more: false,
        })
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/evaluations`) {
        server.listRequests += 1
        if (server.listRequests <= server.listFailures) {
          return jsonResponse({}, { status: 500 })
        }
        if (server.nextListResponse) {
          const response = server.nextListResponse
          delete server.nextListResponse
          return response
        }
        return jsonResponse({ items: server.evaluations, next_cursor: null, has_more: false })
      }
      if (pathname === '/api/v1/evaluations' && request.method === 'POST') {
        server.posts.push((await request.json()) as Record<string, unknown>)
        if (server.createResponse) return server.createResponse
        if (server.createStatus === 409) {
          return jsonResponse(
            { error: { code: 'resource_conflict', message: 'no', details: {}, request_id: 'r' } },
            { status: 409 },
          )
        }
        return jsonResponse(evaluation('queued', { id: NEW_EVAL_ID }), { status: 202 })
      }
      if (
        pathname === `/api/v1/evaluations/${EVAL_ID}` ||
        pathname === `/api/v1/evaluations/${NEW_EVAL_ID}`
      ) {
        return jsonResponse(server.detail)
      }
      if (pathname === `/api/v1/evaluations/${EVAL_ID}/report`) {
        server.reportRequests += 1
        return jsonResponse(server.report)
      }
      return jsonResponse({}, { status: 404 })
    },
  })
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('evaluation in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].evaluation
  const list = `/projects/${PROJECT_ID}/runs/${RUN_ID}/evaluations`
  const detail = `${list}/${EVAL_ID}`

  async function mountList(server: Server) {
    const wrapper = await mountApplicationAt(list, locale, evaluationClient(server))
    await waitFor(() => expect(wrapper.find('.evaluation-list').exists()).toBe(true))
    await waitFor(() =>
      expect(wrapper.find('.evaluation-list-empty, .evaluation').exists()).toBe(true),
    )
    await flushPromises()
    return wrapper
  }

  async function mountDetail(server: Server) {
    const wrapper = await mountApplicationAt(detail, locale, evaluationClient(server))
    await waitFor(() => expect(wrapper.find('.evaluation-detail-facts').exists()).toBe(true))
    return wrapper
  }

  async function openCreationForm(
    wrapper: Awaited<ReturnType<typeof mountApplicationAt>>,
  ): Promise<void> {
    await wrapper.get('.evaluation-list-create').trigger('click')
    await waitFor(() => expect(wrapper.find('.new-evaluation').exists()).toBe(true))
  }

  it('retains a newer method selection when a completed submission tries to navigate', async () => {
    let finish!: (response: Response) => void
    const createResponse = new Promise<Response>((resolve) => {
      finish = resolve
    })
    const server = newServer({ createResponse })
    const wrapper = await mountList(server)
    try {
      await openCreationForm(wrapper)
      await waitFor(() => expect(wrapper.find(`#evaluate-${EXEC.gg}`).exists()).toBe(true))
      await wrapper.get(`#evaluate-${EXEC.gg}`).setValue(false)
      await wrapper.get('.new-evaluation').trigger('submit')
      await waitFor(() => expect(server.posts).toHaveLength(1))
      await wrapper.get(`#evaluate-${EXEC.wiki}`).setValue(false)
      finish(jsonResponse(evaluation('queued', { id: NEW_EVAL_ID }), { status: 202 }))
      await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
      const stay = Array.from(
        document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'),
      ).find((button) => button.textContent?.trim() === catalogues[locale].draftNavigation.stay)
      expect(stay).toBeDefined()
      stay?.click()
      await flushPromises()
      expect(wrapper.vm.$router.currentRoute.value.path).toBe(list)
      expect(wrapper.get<HTMLInputElement>(`#evaluate-${EXEC.wiki}`).element.checked).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })

  it('lists the run evaluations with status, configuration hash and a link', async () => {
    const wrapper = await mountList(newServer({ evaluations: [evaluation('completed')] }))

    const item = wrapper.get('.evaluation')
    expect(item.get('.evaluation-hash').text()).toBe('8'.repeat(64))
    expect(item.text()).toContain('gnd_benchmark_v1')
    expect(item.get('.evaluation-open').attributes('href')).toBe(detail)
  })

  it('hides cached private detail state while session readiness is lost', async () => {
    const wrapper = await mountDetail(newServer())
    try {
      const session = useSessionStore()
      session.status = 'loading'
      await flushPromises()

      expect(wrapper.find('.evaluation-detail-title').exists()).toBe(true)
      expect(wrapper.find('.evaluation-detail-status').exists()).toBe(false)
      expect(wrapper.find('.evaluation-detail-download').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })

  it('announces the initial evaluation-list load through one polite region', async () => {
    let finish!: (response: Response) => void
    const nextListResponse = new Promise<Response>((resolve) => {
      finish = resolve
    })
    const server = newServer({ nextListResponse })
    const wrapper = await mountApplicationAt(list, locale, evaluationClient(server))
    try {
      await waitFor(() =>
        expect(wrapper.find('.evaluation-list [role="status"]').exists()).toBe(true),
      )

      const status = wrapper.get('.evaluation-list [role="status"]')
      expect(status.text()).toBe(catalogues[locale].runs.loading)
      expect(status.attributes('aria-atomic')).toBe('true')

      finish(jsonResponse({ items: [], next_cursor: null, has_more: false }))
      await waitFor(() => expect(wrapper.find('.evaluation-list-empty').exists()).toBe(true))
      expect(wrapper.find('.evaluation-list [role="status"]').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })

  it('announces an evaluation-list failure and permits one in-flight retry', async () => {
    let finish!: (response: Response) => void
    const nextListResponse = new Promise<Response>((resolve) => {
      finish = resolve
    })
    const server = newServer({ listFailures: 1, nextListResponse })
    const wrapper = await mountApplicationAt(list, locale, evaluationClient(server))
    try {
      await waitFor(() => expect(wrapper.find('.evaluation-list-load-error').exists()).toBe(true))

      const feedback = wrapper.get('.evaluation-list-load-error')
      const alert = feedback.get('[role="alert"]')
      const retry = feedback.get('.evaluation-list-retry')
      expect(alert.text()).toBe(messages.loadError)
      expect(alert.attributes('aria-atomic')).toBe('true')
      expect(alert.find('button').exists()).toBe(false)
      expect(feedback.classes()).toContain('app-feedback--critical')

      const firstRetry = retry.trigger('click')
      const duplicateRetry = retry.trigger('click')
      await Promise.all([firstRetry, duplicateRetry])
      await waitFor(() => expect(server.listRequests).toBe(2))
      expect(wrapper.find('.evaluation-list-retry:not([disabled])').exists()).toBe(false)
      expect(server.listRequests).toBe(2)

      finish(jsonResponse({ items: [], next_cursor: null, has_more: false }))
      await waitFor(() => expect(wrapper.find('.evaluation-list-empty').exists()).toBe(true))
      expect(wrapper.find('.evaluation-list-load-error').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })

  it('offers the form only to operators', async () => {
    const viewer = await mountList(newServer({ role: 'viewer' }))
    expect(viewer.find('.new-evaluation').exists()).toBe(false)
    expect(viewer.find('.evaluation-list-create').exists()).toBe(false)
    expect(viewer.get('.evaluation-list-forbidden').text()).toBe(messages.forbidden)
  })

  it('opens the card from the page heading and keeps secondary options collapsed', async () => {
    const wrapper = await mountList(newServer())
    const trigger = wrapper.get('.evaluation-list-create')

    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.new-evaluation').exists()).toBe(false)
    await openCreationForm(wrapper)

    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.evaluation-list-new').classes()).toContain('app-card')
    expect(wrapper.get('.new-evaluation-options').attributes('open')).toBeUndefined()
    expect(document.activeElement?.id).toBe('new-evaluation-heading')
  })

  it('pre-selects what the server accepted last time and sends the ids in run order', async () => {
    const server = newServer({ evaluations: [evaluation('completed')] })
    const wrapper = await mountList(server)
    await openCreationForm(wrapper)
    await waitFor(() => expect(wrapper.find(`#evaluate-${EXEC.gnd}`).exists()).toBe(true))

    const checked = (id: string) =>
      (wrapper.get(`#evaluate-${id}`).element as HTMLInputElement).checked
    expect(checked(EXEC.pq)).toBe(false)
    expect(checked(EXEC.gnd)).toBe(true)
    expect(wrapper.get('.new-evaluation').text()).toContain(messages.new.fromEarlier)

    await wrapper.get('.new-evaluation').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))

    expect(server.posts[0]).toEqual({
      run_id: RUN_ID,
      definition: 'gnd_benchmark_v1',
      method_execution_ids: [EXEC.gnd, EXEC.gg, EXEC.wiki],
      aggregation_execution_id: AGG_ID,
    })
    await waitFor(() => expect(wrapper.find('.evaluation-detail-title').exists()).toBe(true))
  })

  it('starts from every completed execution when there is no earlier evaluation', async () => {
    const server = newServer()
    const wrapper = await mountList(server)
    await openCreationForm(wrapper)
    await waitFor(() => expect(wrapper.find(`#evaluate-${EXEC.pq}`).exists()).toBe(true))

    expect((wrapper.get(`#evaluate-${EXEC.pq}`).element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.get('.new-evaluation').text()).toContain(messages.new.fromAll)
    await wrapper.get(`#evaluate-${EXEC.pq}`).setValue(false)
    await wrapper.get('#evaluate-aggregation').setValue('')
    await wrapper.get('.new-evaluation').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))

    expect(server.posts[0]?.method_execution_ids).toEqual([EXEC.gnd, EXEC.gg, EXEC.wiki])
    expect(server.posts[0]).not.toHaveProperty('aggregation_execution_id')
  })

  it('explains a selection the server refuses and keeps the form', async () => {
    const wrapper = await mountList(newServer({ createStatus: 409 }))
    await openCreationForm(wrapper)
    await waitFor(() => expect(wrapper.find(`#evaluate-${EXEC.pq}`).exists()).toBe(true))

    await wrapper.get('.new-evaluation').trigger('submit')
    await waitFor(() => expect(wrapper.find('.new-evaluation-error').exists()).toBe(true))

    expect(wrapper.get('.new-evaluation-error').text()).toBe(messages.new.errors.notEvaluatable)
  })

  it('shows what produced the evaluation and offers the stored report as a download', async () => {
    const wrapper = await mountDetail(newServer())
    await waitFor(() => expect(wrapper.find('.metric').exists()).toBe(true))

    expect(wrapper.get('.evaluation-detail-hash').text()).toBe('8'.repeat(64))
    expect(wrapper.get('.evaluation-detail-download').attributes('href')).toBe(
      `/api/v1/evaluations/${EVAL_ID}/report`,
    )
    expect(wrapper.get('.evaluation-detail-selection').text()).toContain('3')
    expect(wrapper.get('.evaluation-detail-aggregation').attributes('href')).toContain(AGG_ID)
    expect(wrapper.findAll('.app-card .app-card, .app-card .app-resource-card')).toHaveLength(0)
  })

  it('reports coverage with abstentions and technical errors counted apart', async () => {
    const wrapper = await mountDetail(newServer())
    await waitFor(() => expect(wrapper.find('#coverage-heading').exists()).toBe(true))

    const table = wrapper.get('#coverage-heading').element.parentElement as HTMLElement
    expect(table.querySelector('[role="region"]')?.getAttribute('aria-label')).toBe(
      messages.report.coverage.caption,
    )
    const rows = Array.from(table.querySelectorAll('tbody tr')).map((tr) => tr.textContent ?? '')
    expect(rows[1]).toContain('gender_guesser')
    expect(rows[1]).toMatch(/0[.,]714/)
    const headers = Array.from(table.querySelectorAll('thead th')).map((th) =>
      th.textContent?.trim(),
    )
    expect(headers).toContain(messages.report.coverage.abstained)
    expect(headers).toContain(messages.report.coverage.errors)
  })

  it('separates accuracy from effective accuracy and gives recall with its interval', async () => {
    const wrapper = await mountDetail(newServer())
    await waitFor(() => expect(wrapper.find('#accuracy-heading').exists()).toBe(true))

    const section = wrapper.get('#accuracy-heading').element.parentElement as HTMLElement
    expect(section.querySelector('[role="region"]')?.getAttribute('aria-label')).toBe(
      messages.report.accuracy.caption,
    )
    const first = section.querySelector('tbody tr')?.textContent ?? ''
    expect(first).toMatch(/0[.,]800/)
    expect(first).toMatch(/0[.,]571/)
    expect(first).toMatch(/0[.,]750 \[0[.,]301–0[.,]954\] 3\/4/)
    expect(first).toMatch(/0[.,]333 \[0[.,]061–0[.,]792\] 1\/3/)
    expect(section.textContent).toContain(messages.report.accuracy.effectiveNote)
    expect(section.textContent).toContain('95')
  })

  it('shows a confusion matrix per method with the benchmark in the rows', async () => {
    const wrapper = await mountDetail(newServer())
    await waitFor(() => expect(wrapper.find('.confusion-table').exists()).toBe(true))

    const tables = wrapper.findAll('.confusion-table')
    expect(tables).toHaveLength(2)
    expect(
      wrapper
        .findAll('#confusion-heading ~ .confusion-grid [role="region"]')
        .map((region) => region.attributes('aria-label')),
    ).toEqual(['gender_guesser', 'wiki_gendersort'])
    const rows = tables[0]?.findAll('tbody tr').map((tr) => tr.text()) ?? []
    expect(rows[0]).toMatch(/^male\s*3\s*0\s*0\s*0$/)
    expect(rows[1]).toMatch(/^female\s*1\s*1\s*0\s*0$/)
    expect(tables[0]?.text()).toContain('gender_guesser')
  })

  it('calls the agreement matrix Cohen’s κ between methods, in both directions, with undefined pairs marked', async () => {
    const wrapper = await mountDetail(newServer())
    await waitFor(() => expect(wrapper.find('#kappa-heading').exists()).toBe(true))

    const section = wrapper.get('#kappa-heading').element.parentElement as HTMLElement
    expect(section.querySelector('[role="region"]')?.getAttribute('aria-label')).toBe(
      messages.report.kappa.caption,
    )
    expect(section.textContent).toContain(messages.report.kappa.note)
    const rows = Array.from(section.querySelectorAll('tbody tr')).map((tr) =>
      Array.from(tr.querySelectorAll('th, td')).map((c) =>
        c.textContent?.replace(/\s+/g, ' ').trim(),
      ),
    )
    expect(rows).toHaveLength(3)
    // gender_guesser × wiki_gendersort appears mirrored, and gender_guesser × hivoto_xgboost is undefined.
    expect(rows[0]?.[2]).toMatch(/0[.,]615/)
    expect(rows[1]?.[1]).toMatch(/0[.,]615/)
    expect(rows[0]?.[3]).toContain(messages.report.kappa.undefinedShort)
    expect(rows[0]?.[1]).toBe('—')
  })

  it('describes the ensemble with tokens beside glosses and the review counts', async () => {
    const wrapper = await mountDetail(newServer())
    await waitFor(() => expect(wrapper.find('#ensemble-heading').exists()).toBe(true))

    const section = wrapper.get('#ensemble-heading').element.parentElement as HTMLElement
    expect(
      Array.from(section.querySelectorAll('[role="region"]'), (region) =>
        region.getAttribute('aria-label'),
      ),
    ).toEqual([
      messages.report.ensemble.labels,
      messages.report.ensemble.agreement,
      messages.report.ensemble.certainty,
    ])
    expect(section.textContent).toContain('contested')
    expect(section.textContent).toContain(catalogues[locale].review.gloss.certainty.contested)
    expect(section.textContent).toContain(
      messages.report.ensemble.review.replace('{reviewed}', '3').replace('{corrected}', '1'),
    )
  })

  it('never shows a confidence column, since a method’s confidence is not comparable', async () => {
    const wrapper = await mountDetail(newServer())
    await waitFor(() => expect(wrapper.find('.confusion-table').exists()).toBe(true))

    // Column headers only: a tier's plain-language gloss ("LLM only, high confidence") sits in a row header.
    const headers = wrapper.findAll('thead th').map((th) => th.text())
    expect(headers.some((text) => /onfiden[cz]/.test(text) && !/interval/i.test(text))).toBe(false)
  })

  it('says so when there is no aggregation, and when the report is malformed', async () => {
    const noEnsemble = await mountDetail(newServer({ report: { ...REPORT, ensemble: null } }))
    await waitFor(() => expect(noEnsemble.find('#ensemble-heading').exists()).toBe(true))
    expect(noEnsemble.get('#ensemble-heading').element.parentElement?.textContent).toContain(
      messages.report.ensemble.none,
    )
    document.body.replaceChildren()

    const broken = await mountDetail(newServer({ report: { definition: 'gnd_benchmark_v1' } }))
    await waitFor(() => expect(broken.find('.evaluation-detail-report-error').exists()).toBe(true))
    expect(broken.get('.evaluation-detail-report-error').text()).toBe(messages.report.shapeError)
    expect(broken.find('.metric').exists()).toBe(false)
  })

  it('renders every section of the report the real backend stored', async () => {
    const wrapper = await mountDetail(newServer({ report: realReport }))
    await waitFor(() => expect(wrapper.findAll('.metric')).toHaveLength(5))

    // Eight methods in the agreement matrix, as in the published study: twenty-eight pairs, shown in both directions.
    expect(wrapper.findAll('#kappa-heading ~ .app-scroll-frame tbody tr')).toHaveLength(8)
    // One confusion matrix per scored method.
    expect(wrapper.findAll('.confusion-table')).toHaveLength(7)
    expect(wrapper.get('.evaluation-detail-benchmark').text()).toContain('7')
  })

  it('waits for a running evaluation and asks for no report yet', async () => {
    const server = newServer({ detail: evaluation('running') })
    const wrapper = await mountDetail(server)

    expect(wrapper.get('.evaluation-detail-waiting').text()).toBe(messages.detail.waiting)
    expect(server.reportRequests).toBe(0)
    expect(wrapper.find('.evaluation-detail-download').exists()).toBe(false)
  })

  it('shows why an evaluation failed', async () => {
    const wrapper = await mountDetail(
      newServer({
        detail: evaluation('failed', {
          failure_class: 'EvaluationError',
          failure_diagnostic: 'no benchmark entries',
        }),
      }),
    )

    expect(wrapper.get('.evaluation-detail-failure-class').text()).toBe('EvaluationError')
    expect(wrapper.get('.evaluation-detail-failure').text()).toContain('no benchmark entries')
  })
})
