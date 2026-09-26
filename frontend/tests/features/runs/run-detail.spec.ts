import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { mountApplicationAt } from '../../helpers/render'
import { expectNoAxeViolations } from '../../helpers/axe'
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
      if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
        return jsonResponse({
          id: PROJECT_ID,
          slug: 'p',
          display_name: 'Project A',
          current_user_role: 'viewer',
          working_aggregation_execution_id: null,
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
      if (pathname === `/api/v1/runs/${RUN_ID}`) {
        server.runGets += 1
        return jsonResponse(server.run)
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/executions`) {
        server.executionGets += 1
        return jsonResponse(server.executions)
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/aggregations`) {
        return jsonResponse({ items: [], next_cursor: null, has_more: false })
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

  it('puts a successful outcome before compact method evidence and labels every control', async () => {
    const wrapper = await mountDetail(
      server({
        run: runBody('completed_with_errors', progress(7, 1, 8)),
        executions: [executionBody('completed_with_errors', progress(3, 1, 4))],
      }),
    )
    await waitFor(() => expect(wrapper.find('.aggregations-empty').exists()).toBe(true))

    const sections = Array.from(wrapper.get('.run-detail').element.children)
    expect(sections.indexOf(wrapper.get('.aggregations').element)).toBeLessThan(
      sections.indexOf(wrapper.get('.run-detail-executions').element),
    )
    expect(wrapper.get('.run-detail-title').text()).not.toBe(messages.detail.title)
    expect(wrapper.findAll('.run-detail-summary dt').map((item) => item.text())).toEqual([
      messages.detail.status,
      messages.detail.created,
      messages.detail.progress,
    ])
    expect(wrapper.get('.execution').classes()).toContain('execution--compact')
    expect(wrapper.find('.execution progress').exists()).toBe(false)
    expect(wrapper.get('.run-detail-execution-summary').text()).toBe(
      messages.detail.methodCountWithIssues.replace('{count}', '1').replace('{issues}', '1'),
    )
    expect(wrapper.get('.execution-provenance summary').attributes('aria-label')).toBe(
      messages.execution.provenanceFor.replace('{method}', 'gender_guesser'),
    )
    await expectNoAxeViolations(wrapper.get('main').element)
  })

  it('keeps the combined-result step after methods while a run is active', async () => {
    const wrapper = await mountDetail(server())
    const sections = Array.from(wrapper.get('.run-detail').element.children)

    expect(sections.indexOf(wrapper.get('.aggregations').element)).toBeGreaterThan(
      sections.indexOf(wrapper.get('.run-detail-executions').element),
    )
  })

  it('opens a completed method’s decisions from its method name', async () => {
    const wrapper = await mountDetail(
      server({
        run: runBody('completed', progress(8, 0, 8)),
        executions: [executionBody('completed', progress(4, 0, 4))],
      }),
    )

    expect(wrapper.get('.execution-name a').attributes('href')).toBe(
      path + '/executions/' + EXECUTION_ID + '/results',
    )
  })

  it('opens a cancelled method’s retained decisions from its method name', async () => {
    const wrapper = await mountDetail(
      server({
        run: runBody('cancelled', progress(3, 1, 8)),
        executions: [executionBody('cancelled', progress(3, 1, 4))],
      }),
    )

    expect(wrapper.get('.execution-name a').attributes('href')).toBe(
      path + '/executions/' + EXECUTION_ID + '/results',
    )
  })

  it('does not present a decision link while a method is still running', async () => {
    const wrapper = await mountDetail(server())

    expect(wrapper.find('.execution-name a').exists()).toBe(false)
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

  it('reads back the run provenance and says so when a value was not recorded', async () => {
    const wrapper = await mountDetail(
      server({
        run: runBody('completed', progress(8, 0, 8), {
          code_git_commit: 'a'.repeat(40),
          dependency_lock_sha256: 'b'.repeat(64),
          container_image_digest: null,
        }),
      }),
    )

    const fact = (key: string) => wrapper.get(`.provenance-fact[data-key="${key}"] dd`).text()
    expect(fact('codeCommit')).toBe('a'.repeat(40))
    expect(fact('dependencyLockHash')).toBe('b'.repeat(64))
    expect(fact('configHash')).toBe('e'.repeat(64))
    expect(fact('imageDigest')).toBe(messages.provenance.notRecorded)
    expect(wrapper.get('.provenance').element.tagName).toBe('DETAILS')
    expect(wrapper.get('.provenance').attributes('open')).toBeUndefined()
    const sections = Array.from(wrapper.get('.run-detail').element.children)
    expect(sections.indexOf(wrapper.get('.provenance').element)).toBeGreaterThan(
      sections.indexOf(wrapper.get('.run-detail-executions').element),
    )
  })

  it('does not stream or show method results for a run from a different snapshot', async () => {
    const state = server({
      run: runBody('running', progress(0, 0, 8), { dataset_snapshot_id: 'other-snapshot' }),
    })
    const wrapper = await mountApplicationAt(path, locale, detailClient(state))
    await waitFor(() => expect(wrapper.find('.run-detail-unavailable').exists()).toBe(true))
    expect(wrapper.find('.run-detail-executions').exists()).toBe(false)
    expect(FakeEventSource.instances).toHaveLength(0)
    expect(state.executionGets).toBe(0)
    wrapper.unmount()
  })

  it('shows each method execution its own model and prompt identity, only where it has one', async () => {
    const wrapper = await mountDetail(
      server({
        run: runBody('completed', progress(8, 0, 8)),
        executions: [
          executionBody('completed', progress(4, 0, 4), {
            method_name: 'local_llm',
            model_identifier: 'llama3',
            model_revision: 'rev-7',
            prompt_version: 'prompt_v2',
          }),
        ],
      }),
    )

    const labels = wrapper.findAll('.execution-provenance-fact dt').map((dt) => dt.text())
    expect(labels).toContain(messages.execution.modelIdentifier)
    expect(labels).toContain(messages.execution.promptVersion)
    expect(labels).not.toContain(messages.execution.schemaVersion)
    expect(labels).not.toContain(messages.execution.modelChecksum)
    expect(wrapper.text()).toContain('llama3')
    expect(wrapper.text()).toContain('prompt_v2')
  })

  it('closes the stream when the screen is left', async () => {
    const wrapper = await mountDetail(server())
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))

    wrapper.unmount()

    expect(stream().closed).toBe(true)
  })
})
