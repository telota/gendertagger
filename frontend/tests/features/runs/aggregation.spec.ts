import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { getDialogButtonByName, mountApplicationAt, queryDialogByName } from '../../helpers/render'
import { expectNoAxeViolations } from '../../helpers/axe'
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
const EXEC_A = 'e0000000-0000-0000-0000-00000000000a'
const EXEC_B = 'e0000000-0000-0000-0000-00000000000b'
const EXEC_C = 'e0000000-0000-0000-0000-00000000000c'
const AGG_ID = 'f0000000-0000-0000-0000-000000000001'
const HISTORY_AGG_ID = 'f0000000-0000-0000-0000-000000000002'

const progress = { completed: 4, failed: 0, total: 4, percentage: 100 }

function execution(id: string, method: string, status = 'completed') {
  return {
    id,
    run_id: RUN_ID,
    method_name: method,
    status,
    progress,
    completed_count: 4,
    failed_count: 0,
    total_count: 4,
    implementation_version: `${method}_v1`,
    normalization_version: `${method}_v1`,
    config_sha256: 'f'.repeat(64),
    resolved_config: {},
    created_at: '2026-01-01T10:00:00Z',
  }
}

function aggregation(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: AGG_ID,
    run_id: RUN_ID,
    strategy: 'reference_v1',
    status,
    resolved_config: {},
    method_execution_ids: [EXEC_A, EXEC_B],
    config_sha256: '9'.repeat(64),
    created_at: '2026-01-01T11:00:00Z',
    ...extra,
  }
}

interface Server {
  runStatus: string
  role: 'operator' | 'viewer'
  workingAggregationId: string | null
  executions: ReturnType<typeof execution>[]
  aggregations: ReturnType<typeof aggregation>[]
  /** What `POST /runs/{id}/aggregations` answers. */
  postStatus: 200 | 202 | 409
  posts: { method_execution_ids: string[]; strategy: string }[]
  postGate?: Promise<void>
}

function newServer(overrides: Partial<Server> = {}): Server {
  return {
    runStatus: 'completed',
    role: 'operator',
    workingAggregationId: null,
    executions: [
      execution(EXEC_A, 'gender_guesser'),
      execution(EXEC_B, 'gnd'),
      execution(EXEC_C, 'hivoto_xgboost', 'completed_with_errors'),
    ],
    aggregations: [],
    postStatus: 202,
    posts: [],
    ...overrides,
  }
}

function aggregationClient(server: Server) {
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
          current_user_role: server.role,
          created_at: '2026-01-01T00:00:00Z',
          working_aggregation_execution_id: server.workingAggregationId,
        })
      }
      if (pathname === `/api/v1/runs/${RUN_ID}`) {
        return jsonResponse({
          id: RUN_ID,
          dataset_snapshot_id: SNAPSHOT_ID,
          status: server.runStatus,
          created_at: '2026-01-01T10:00:00Z',
          config_sha256: 'e'.repeat(64),
          resolved_config: { methods: [] },
          progress,
          application_version: '1',
          code_git_commit: 'abc',
          python_version: '3.12',
        })
      }
      if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}`) {
        return jsonResponse({
          id: SNAPSHOT_ID,
          project_id: PROJECT_ID,
          status: 'ready',
          created_at: '2026-01-01T09:00:00Z',
        })
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/executions`) return jsonResponse(server.executions)
      if (pathname === `/api/v1/runs/${RUN_ID}/aggregations`) {
        if (request.method === 'POST') {
          server.posts.push((await request.json()) as Server['posts'][number])
          if (server.postGate) await server.postGate
          if (server.postStatus === 409) {
            return jsonResponse(
              { error: { code: 'resource_conflict', message: 'no', details: {}, request_id: 'r' } },
              { status: 409 },
            )
          }
          const created = aggregation('queued')
          if (server.postStatus === 202) server.aggregations = [created]
          return jsonResponse(created, { status: server.postStatus })
        }
        return jsonResponse({ items: server.aggregations, next_cursor: null, has_more: false })
      }
      if (pathname === `/api/v1/aggregations/${AGG_ID}`) {
        return jsonResponse(server.aggregations[0] ?? aggregation('completed'))
      }
      return jsonResponse({}, { status: 404 })
    },
  })
}

beforeEach(() => {
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

describe.each(['de', 'en'] as const)('aggregation in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].aggregations
  const runPath = `/projects/${PROJECT_ID}/snapshots/${SNAPSHOT_ID}/runs/${RUN_ID}`

  async function mountRun(server: Server) {
    const wrapper = await mountApplicationAt(runPath, locale, aggregationClient(server))
    await waitFor(() => expect(wrapper.find('.aggregations').exists()).toBe(true))
    await waitFor(() =>
      expect(wrapper.find('.aggregations-empty, .aggregation').exists()).toBe(true),
    )
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 20))
    await flushPromises()
    return wrapper
  }

  it('creates the default reference aggregation once a run has finished, with every completed execution in the server order', async () => {
    const server = newServer()
    await mountRun(server)

    await waitFor(() => expect(server.posts).toHaveLength(1))
    expect(server.posts[0]).toEqual({
      method_execution_ids: [EXEC_A, EXEC_B, EXEC_C],
      strategy: 'reference_v1',
    })
  })

  it('does not create anything for a viewer, a running run or when a usable aggregation exists', async () => {
    const viewer = newServer({ role: 'viewer' })
    await mountRun(viewer)
    const running = newServer({ runStatus: 'running' })
    const wrapperRunning = await mountRun(running)
    const existing = newServer({ aggregations: [aggregation('completed')] })
    await mountRun(existing)
    await flushPromises()

    expect(viewer.posts).toHaveLength(0)
    expect(running.posts).toHaveLength(0)
    expect(existing.posts).toHaveLength(0)
    expect(wrapperRunning.get('.aggregations-waiting').text()).toBe(messages.waitingForRun)
  })

  it('makes a failed automatic attempt visible instead of swallowing it', async () => {
    const server = newServer({ postStatus: 409 })
    const wrapper = await mountRun(server)

    await waitFor(() =>
      expect(wrapper.get('.aggregations-error').text()).toBe(messages.errors.autoNotAggregatable),
    )
    // ADR-0051: a `resource_conflict` always retries once as `reference_partial_v1` before giving
    // up — this deployment rejects that too, so the error shown is still "not aggregatable".
    expect(server.posts).toHaveLength(2)
    expect(server.posts[0]?.strategy).toBe('reference_v1')
    expect(server.posts[1]?.strategy).toBe('reference_partial_v1')
  })

  it('separates the working result, method lineage, next action and history', async () => {
    const working = aggregation('completed')
    const newerAlternative = aggregation('completed', {
      id: HISTORY_AGG_ID,
      method_execution_ids: [EXEC_A, EXEC_C],
      created_at: '2026-01-01T12:00:00Z',
    })
    const wrapper = await mountRun(
      newServer({
        workingAggregationId: AGG_ID,
        aggregations: [newerAlternative, working],
      }),
    )

    const featured = wrapper.get('.aggregation--featured')
    expect(featured.get('.aggregation-title').text()).toBe(messages.currentWorking)
    expect(featured.text()).toContain(messages.item.referenceStrategy)
    expect(featured.text()).toContain('hivoto_xgboost')
    expect(featured.get('.aggregation-excluded').text()).toContain(
      catalogues[locale].runs.status.completedWithErrors,
    )
    expect(featured.get('.app-button').text()).toBe(messages.item.review)
    expect(featured.get('.app-button').attributes('href')).toBe(
      `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/review`,
    )
    expect(wrapper.text()).not.toContain('9'.repeat(64))
    expect(wrapper.get('.aggregations-history').text()).toContain(
      messages.historyWithCount.replace('{count}', '1'),
    )

    await featured.get('.aggregation-selection summary').trigger('click')
    await wrapper.get('.aggregations-history > summary').trigger('click')
    await expectNoAxeViolations(wrapper.get('main').element)
  })

  it('re-aggregates from a chosen subset, in the server order, and reports an identical existing one', async () => {
    const server = newServer({ aggregations: [aggregation('completed')], postStatus: 200 })
    const wrapper = await mountRun(server)

    await wrapper.get('.aggregations-advanced summary').trigger('click')
    await wrapper.get(`#aggregate-${EXEC_B}`).setValue(false)
    await wrapper.get('.aggregations-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))

    expect(server.posts[0]?.method_execution_ids).toEqual([EXEC_A])
    await waitFor(() => expect(wrapper.find('.aggregations-reused').exists()).toBe(true))
    expect(wrapper.get('.aggregations-reused').text()).toContain(messages.reused)
  })

  it('cannot submit an empty selection', async () => {
    const wrapper = await mountRun(newServer({ aggregations: [aggregation('completed')] }))

    for (const id of [EXEC_A, EXEC_B, EXEC_C]) {
      await wrapper.get(`#aggregate-${id}`).setValue(false)
    }

    expect(wrapper.get('.aggregations-submit').attributes('disabled')).toBeDefined()
  })

  it('reads back the configuration hash, the resolved configuration and the selection by method name', async () => {
    const server = newServer({ aggregations: [aggregation('completed')] })
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}`,
      locale,
      aggregationClient(server),
    )
    await waitFor(() => expect(wrapper.find('.aggregation-detail-title').exists()).toBe(true))
    await waitFor(() =>
      expect(wrapper.find('.aggregation-detail-selection li').exists()).toBe(true),
    )

    expect(wrapper.get('.aggregation-detail-facts dd code').text()).toBe('9'.repeat(64))
    expect(wrapper.get('[aria-labelledby="aggregation-config-heading"] pre').text()).toBe('{}')
    expect(
      wrapper.findAll('.aggregation-detail-selection li').map((entry) => entry.get('span').text()),
    ).toEqual(['gender_guesser', 'gnd'])
    expect(wrapper.get('.aggregation-detail-back').attributes('href')).toBe(runPath)
    // A finished aggregation opens the queues and the whole register.
    expect(wrapper.get('.aggregation-detail-people').attributes('href')).toBe(
      `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/people`,
    )
    expect(
      wrapper.get('.aggregation-detail-review:not(.aggregation-detail-people)').attributes('href'),
    ).toBe(`/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/review`)
    const headingActions = wrapper.findAll('.aggregation-detail-actions .app-button--text')
    expect(headingActions).toHaveLength(3)
    // The exit criterion: the code that produced the aggregation's run is readable from here.
    expect(wrapper.get('.provenance-fact[data-key="codeCommit"] dd').text()).toBe('abc')
    expect(wrapper.get('.provenance-fact[data-key="configHash"] dd').text()).toBe('e'.repeat(64))
  })

  it('protects a changed manual selection and keeps failed creation dirty', async () => {
    const server = newServer({ aggregations: [aggregation('completed')], postStatus: 409 })
    const wrapper = await mountRun(server)
    await wrapper.get(`#aggregate-${EXEC_C}`).setValue(true)
    await wrapper.get('.aggregations-form').trigger('submit')
    await waitFor(() =>
      expect(wrapper.get('.aggregations-error').text()).toBe(messages.errors.notAggregatable),
    )
    const attempt = wrapper.vm.$router.push('/')
    await waitFor(() =>
      expect(queryDialogByName(catalogues[locale].draftNavigation.title)).not.toBeNull(),
    )
    getDialogButtonByName(
      catalogues[locale].draftNavigation.title,
      catalogues[locale].draftNavigation.stay,
    ).click()
    await attempt
    expect(wrapper.vm.$route.path).toBe(runPath)
    expect((wrapper.get(`#aggregate-${EXEC_C}`).element as HTMLInputElement).checked).toBe(true)
    expect(server.posts).toHaveLength(2)
    expect(server.posts[1]?.strategy).toBe('reference_partial_v1')
    wrapper.unmount()
  })

  it('marks a successfully submitted manual selection clean without resetting it', async () => {
    const server = newServer({ aggregations: [aggregation('completed')], postStatus: 200 })
    const wrapper = await mountRun(server)
    await wrapper.get(`#aggregate-${EXEC_C}`).setValue(true)
    await wrapper.get('.aggregations-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.aggregations-reused').exists()).toBe(true))
    expect((wrapper.get(`#aggregate-${EXEC_C}`).element as HTMLInputElement).checked).toBe(true)
    const attempt = wrapper.vm.$router.push('/')
    await flushPromises()
    expect(queryDialogByName(catalogues[locale].draftNavigation.title)).toBeNull()
    await attempt
    expect(server.posts).toHaveLength(1)
    wrapper.unmount()
  })

  it('keeps a selection changed during the request dirty after its earlier submission succeeds', async () => {
    let release!: () => void
    const server = newServer({
      aggregations: [aggregation('completed')],
      postStatus: 200,
      postGate: new Promise<void>((resolve) => {
        release = resolve
      }),
    })
    const wrapper = await mountRun(server)
    await wrapper.get(`#aggregate-${EXEC_C}`).setValue(true)
    await wrapper.get('.aggregations-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))
    await wrapper.get(`#aggregate-${EXEC_B}`).setValue(false)
    release()
    await waitFor(() => expect(wrapper.find('.aggregations-reused').exists()).toBe(true))
    const attempt = wrapper.vm.$router.push('/')
    await waitFor(() =>
      expect(queryDialogByName(catalogues[locale].draftNavigation.title)).not.toBeNull(),
    )
    getDialogButtonByName(
      catalogues[locale].draftNavigation.title,
      catalogues[locale].draftNavigation.stay,
    ).click()
    await attempt
    expect(wrapper.vm.$route.path).toBe(runPath)
    expect((wrapper.get(`#aggregate-${EXEC_B}`).element as HTMLInputElement).checked).toBe(false)
    expect(server.posts[0]?.method_execution_ids).toEqual([EXEC_A, EXEC_B, EXEC_C])
    wrapper.unmount()
  })
})
