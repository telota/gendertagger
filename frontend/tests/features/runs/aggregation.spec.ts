import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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
const EXEC_A = 'e0000000-0000-0000-0000-00000000000a'
const EXEC_B = 'e0000000-0000-0000-0000-00000000000b'
const EXEC_C = 'e0000000-0000-0000-0000-00000000000c'
const AGG_ID = 'f0000000-0000-0000-0000-000000000001'

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
  executions: ReturnType<typeof execution>[]
  aggregations: ReturnType<typeof aggregation>[]
  /** What `POST /runs/{id}/aggregations` answers. */
  postStatus: 200 | 202 | 409
  posts: { method_execution_ids: string[]; strategy: string }[]
}

function newServer(overrides: Partial<Server> = {}): Server {
  return {
    runStatus: 'completed',
    role: 'operator',
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
      if (pathname === `/api/v1/runs/${RUN_ID}/executions`) return jsonResponse(server.executions)
      if (pathname === `/api/v1/runs/${RUN_ID}/aggregations`) {
        if (request.method === 'POST') {
          server.posts.push((await request.json()) as Server['posts'][number])
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
    expect(server.posts).toHaveLength(1)
  })

  it('lists aggregations with strategy, selection size and configuration hash', async () => {
    const wrapper = await mountRun(newServer({ aggregations: [aggregation('completed')] }))

    const item = wrapper.get('.aggregation')
    expect(item.text()).toContain('reference_v1')
    expect(item.get('.aggregation-hash').text()).toBe('9'.repeat(64))
    expect(item.get('.aggregation-status').text()).toBe(catalogues[locale].runs.status.completed)
  })

  it('re-aggregates from a chosen subset, in the server order, and reports an identical existing one', async () => {
    const server = newServer({ aggregations: [aggregation('completed')], postStatus: 200 })
    const wrapper = await mountRun(server)

    await wrapper.get('.aggregations-advanced summary').trigger('click')
    await wrapper.get(`#aggregate-${EXEC_C}`).setValue(false)
    await wrapper.get('.aggregations-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))

    expect(server.posts[0]?.method_execution_ids).toEqual([EXEC_A, EXEC_B])
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
    await waitFor(() => expect(wrapper.find('.aggregation-detail-method').exists()).toBe(true))

    expect(wrapper.get('.aggregation-detail-hash').text()).toBe('9'.repeat(64))
    expect(wrapper.get('.aggregation-detail-config').text()).toBe('{}')
    expect(wrapper.findAll('.aggregation-detail-method').map((m) => m.text())).toEqual([
      'gender_guesser',
      'gnd',
    ])
    expect(wrapper.get('.aggregation-detail-back').attributes('href')).toBe(runPath)
    // The exit criterion: the code that produced the aggregation's run is readable from here.
    expect(wrapper.get('.provenance-fact[data-key="codeCommit"] dd').text()).toBe('abc')
    expect(wrapper.get('.provenance-fact[data-key="configHash"] dd').text()).toBe('e'.repeat(64))
  })
})
