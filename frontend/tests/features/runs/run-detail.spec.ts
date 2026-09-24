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

/** jsdom has no EventSource; this one lets a test open, feed, fail and inspect the stream. */
class FakeEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  static instances: FakeEventSource[] = []

  readyState = FakeEventSource.CONNECTING
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  private listeners = new Map<string, ((event: Event) => void)[]>()

  constructor(
    readonly url: string,
    readonly init?: EventSourceInit,
  ) {
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: Event) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  close(): void {
    this.closed = true
    this.readyState = FakeEventSource.CLOSED
  }

  open(): void {
    this.readyState = FakeEventSource.OPEN
    this.onopen?.()
  }

  emit(type: string, payload: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(payload) })
    for (const listener of this.listeners.get(type) ?? []) listener(event)
  }

  /** The browser retries by itself (CONNECTING) or gives up (CLOSED, e.g. a refused request). */
  fail(readyState: number): void {
    this.readyState = readyState
    this.onerror?.()
  }
}

const catalogues = { de, en } as const
const USER = { id: 'a0000000-0000-0000-0000-000000000002', display_name: 'Op', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
const RUN_ID = 'd0000000-0000-0000-0000-000000000001'
const EXECUTION_ID = 'e0000000-0000-0000-0000-000000000001'

const progress = (completed: number, failed: number, total: number) => ({
  completed,
  failed,
  total,
  percentage: Math.round(((completed + failed) / total) * 100),
})

function runBody(status: string, p = progress(0, 0, 8), extra: Record<string, unknown> = {}) {
  return {
    id: RUN_ID,
    dataset_snapshot_id: SNAPSHOT_ID,
    status,
    created_at: '2026-01-01T10:00:00Z',
    config_sha256: 'e'.repeat(64),
    resolved_config: { methods: [] },
    progress: p,
    application_version: '1',
    code_git_commit: 'abc',
    python_version: '3.12',
    ...extra,
  }
}

function executionBody(status: string, p = progress(0, 0, 4), extra: Record<string, unknown> = {}) {
  return {
    id: EXECUTION_ID,
    run_id: RUN_ID,
    method_name: 'gender_guesser',
    status,
    progress: p,
    completed_count: p.completed,
    failed_count: p.failed,
    total_count: p.total,
    implementation_version: 'v1',
    normalization_version: 'v1',
    config_sha256: 'f'.repeat(64),
    resolved_config: {},
    created_at: '2026-01-01T10:00:00Z',
    ...extra,
  }
}

interface Server {
  run: ReturnType<typeof runBody>
  executions: ReturnType<typeof executionBody>[]
  runGets: number
  executionGets: number
}

function detailClient(server: Server) {
  return createApiClient({
    fetch: async (request) => {
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/branding') return jsonResponse({})
      if (pathname === '/api/v1/me') return jsonResponse(USER)
      if (pathname === '/api/v1/auth/session') {
        return jsonResponse({ must_change_password: false, keep_signed_in: false })
      }
      if (pathname === `/api/v1/runs/${RUN_ID}`) {
        server.runGets += 1
        return jsonResponse(server.run)
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/executions`) {
        server.executionGets += 1
        return jsonResponse(server.executions)
      }
      return jsonResponse({}, { status: 404 })
    },
  })
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('run detail with live progress in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].runs
  const path = `/projects/${PROJECT_ID}/snapshots/${SNAPSHOT_ID}/runs/${RUN_ID}`

  async function mountDetail(server: Server) {
    const wrapper = await mountApplicationAt(path, locale, detailClient(server))
    await waitFor(() => expect(wrapper.find('.run-detail-title').exists()).toBe(true))
    await waitFor(() => expect(wrapper.find('.execution').exists()).toBe(true))
    return wrapper
  }

  function server(overrides: Partial<Server> = {}): Server {
    return {
      run: runBody('running'),
      executions: [executionBody('running')],
      runGets: 0,
      executionGets: 0,
      ...overrides,
    }
  }

  const stream = (): FakeEventSource => {
    const [first] = FakeEventSource.instances
    if (!first) throw new Error('no stream was opened')
    return first
  }

  it('opens the run event stream for a run that is still going and says when it is live', async () => {
    const wrapper = await mountDetail(server())

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    expect(stream().url).toBe(`/api/v1/runs/${RUN_ID}/events`)
    expect(wrapper.get('.run-detail-connection').text()).toBe(messages.detail.connection.connecting)

    stream().open()
    await flushPromises()

    expect(wrapper.get('.run-detail-connection').text()).toBe(messages.detail.connection.live)
  })

  it('does not open a stream for a run that has already finished', async () => {
    await mountDetail(server({ run: runBody('completed', progress(8, 0, 8)) }))
    await flushPromises()

    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('moves the bars and counts from progress events without refetching', async () => {
    const state = server()
    const wrapper = await mountDetail(state)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    stream().open()
    const runGetsBefore = state.runGets

    stream().emit('run.progress', {
      run_id: RUN_ID,
      status: 'running',
      progress: progress(4, 0, 8),
    })
    stream().emit('method_execution.progress', {
      method_execution_id: EXECUTION_ID,
      method_name: 'gender_guesser',
      status: 'running',
      progress: progress(3, 1, 4),
    })
    await flushPromises()

    const bars = wrapper.findAll('progress')
    expect(bars[0]?.attributes('value')).toBe('50')
    expect(bars[1]?.attributes('value')).toBe('100')
    expect(wrapper.get('.execution-counts').text()).toMatch(/3.*4.*1/)
    expect(state.runGets).toBe(runGetsBefore)
  })

  it('refetches and closes the stream when the run ends', async () => {
    const state = server()
    const wrapper = await mountDetail(state)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    stream().open()

    state.run = runBody('completed', progress(8, 0, 8), { finished_at: '2026-01-01T10:01:00Z' })
    state.executions = [executionBody('completed', progress(4, 0, 4))]
    stream().emit('run.completed', {
      run_id: RUN_ID,
      status: 'completed',
      progress: progress(8, 0, 8),
    })
    await waitFor(() =>
      expect(wrapper.get('.run-detail-status').text()).toBe(messages.status.completed),
    )

    expect(stream().closed).toBe(true)
    expect(wrapper.get('.execution-status').text()).toBe(messages.status.completed)
    expect(wrapper.get('.run-detail-connection').text()).toBe('')
  })

  it('shows what went wrong per method execution', async () => {
    const wrapper = await mountDetail(
      server({
        run: runBody('completed_with_errors', progress(3, 1, 4)),
        executions: [
          executionBody('failed', progress(0, 4, 4), {
            failure_class: 'ModelUnavailable',
            failure_diagnostic: 'the model server did not answer',
          }),
        ],
      }),
    )

    expect(wrapper.get('.execution-failure-class').text()).toBe('ModelUnavailable')
    expect(wrapper.get('.execution-failure-diagnostic').text()).toBe(
      'the model server did not answer',
    )
    expect(wrapper.get('.run-detail-status').text()).toBe(messages.status.completedWithErrors)
  })

  it('refetches after a re-connection, since no event log is replayed', async () => {
    const state = server()
    const wrapper = await mountDetail(state)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    stream().open()
    await flushPromises()
    const runGetsBefore = state.runGets
    const executionGetsBefore = state.executionGets

    // The browser retries by itself after a network error and reports it as CONNECTING.
    stream().fail(FakeEventSource.CONNECTING)
    await flushPromises()
    expect(wrapper.get('.run-detail-connection').text()).toBe(
      messages.detail.connection.reconnecting,
    )
    stream().open()
    await waitFor(() => expect(state.runGets).toBeGreaterThan(runGetsBefore))

    expect(state.executionGets).toBeGreaterThan(executionGetsBefore)
    expect(wrapper.get('.run-detail-connection').text()).toBe(messages.detail.connection.live)
  })

  it('opens a new connection with backoff when the request is refused outright', async () => {
    const state = server()
    await mountDetail(state)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    stream().open()
    await flushPromises()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const runGetsBefore = state.runGets

    stream().fail(FakeEventSource.CLOSED)
    expect(FakeEventSource.instances).toHaveLength(1)
    vi.advanceTimersByTime(1000)

    expect(FakeEventSource.instances).toHaveLength(2)
    vi.useRealTimers()
    await waitFor(() => expect(state.runGets).toBeGreaterThan(runGetsBefore))
  })

  it('closes the stream when the screen is left', async () => {
    const wrapper = await mountDetail(server())
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))

    wrapper.unmount()

    expect(stream().closed).toBe(true)
  })
})
