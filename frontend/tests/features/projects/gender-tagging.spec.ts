import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Operator One', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
const RUN_ID = 'd0000000-0000-0000-0000-000000000001'
const EXEC_A = 'e0000000-0000-0000-0000-000000000001'
const EXEC_B = 'e0000000-0000-0000-0000-000000000002'
const AGGREGATION_ID = 'f0000000-0000-0000-0000-000000000001'
const EXPORT_ID = '10000000-0000-0000-0000-000000000001'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function project(workingAggregationId: string | null) {
  return {
    id: PROJECT_ID,
    slug: 'gender-project',
    display_name: 'Gender Project',
    description: null,
    current_user_role: 'operator',
    current_user_can_manage_members: false,
    game_mode_enabled: false,
    manager_user_id: USER.id,
    created_by_user_id: USER.id,
    working_aggregation_execution_id: workingAggregationId,
    team: {
      id: 'team-1',
      slug: 'team',
      display_name: 'Editorial team',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    created_at: '2026-01-01T00:00:00Z',
  }
}

const READY_SNAPSHOT = {
  id: SNAPSHOT_ID,
  project_id: PROJECT_ID,
  status: 'ready',
  record_count: 42,
  created_at: '2026-01-01T00:00:00Z',
  ready_at: '2026-01-01T00:05:00Z',
  parser_version: 1,
  source_sha256: 'x'.repeat(64),
  import_config: { source_format: 'tei', packaging: 'single' },
  failure_diagnostic: null,
}

const AGGREGATION = {
  id: AGGREGATION_ID,
  run_id: RUN_ID,
  status: 'completed',
  strategy: 'reference_v1',
  method_execution_ids: [EXEC_A, EXEC_B],
  config_sha256: 'y'.repeat(64),
  created_at: '2026-01-01T00:10:00Z',
}

function routesFor(workingAggregationId: string | null) {
  let working = workingAggregationId
  const routes = new Map<string, unknown>([
    ['/api/v1/branding', {}],
    ['/api/v1/me', USER],
    ['/api/v1/auth/session', { must_change_password: false, keep_signed_in: false }],
    [
      '/api/v1/me/preferences',
      { locale: null, theme: 'system', desktop_sidebar_collapsed: false, interface_mode: 'guided', revision: 1 },
    ],
    [`/api/v1/projects/${PROJECT_ID}/snapshots`, { items: [READY_SNAPSHOT], has_more: false, next_cursor: null }],
    ['/api/v1/methods', [
      { name: 'method-a', implementation_version: '1', method_confidence_range: [0, 1] },
      { name: 'method-b', implementation_version: '1', method_confidence_range: [0, 1] },
    ]],
    [
      `/api/v1/runs/${RUN_ID}`,
      { id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID, status: 'completed', created_at: '2026-01-01T00:00:00Z' },
    ],
    [
      `/api/v1/runs/${RUN_ID}/executions`,
      [
        { id: EXEC_A, run_id: RUN_ID, method_name: 'method-a', status: 'completed' },
        { id: EXEC_B, run_id: RUN_ID, method_name: 'method-b', status: 'completed' },
      ],
    ],
    [`/api/v1/aggregations/${AGGREGATION_ID}`, AGGREGATION],
  ])
  return {
    get: (pathname: string) => routes.get(pathname),
    get working() {
      return working
    },
    set working(value: string | null) {
      working = value
    },
  }
}

enableAutoUnmount(afterEach)

afterEach(() => {
  document.body.replaceChildren()
  vi.unstubAllGlobals()
})

describe.each(['de', 'en'] as const)('GenderTaggingView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].genderTagging

  function stubEventSource(): void {
    vi.stubGlobal(
      'EventSource',
      class {
        static readonly CLOSED = 2
        readyState = 0
        addEventListener(): void {}
        close(): void {}
      },
    )
  }

  it('shows project facts and the import toggle for an operator', async () => {
    stubEventSource()
    const table = routesFor(null)
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path === `/api/v1/projects/${PROJECT_ID}`) return Promise.resolve(jsonResponse(project(null)))
        const route = table.get(path)
        return Promise.resolve(jsonResponse(route ?? {}, { status: route === undefined ? 404 : 200 }))
      },
    })
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/gender-tagging`,
      locale,
      client,
    )
    await waitFor(() => expect(wrapper.get('h1').text()).toBe('Gender Project'))
    expect(wrapper.text()).toContain('gender-project')
    expect(wrapper.text()).toContain('Editorial team')
    expect(wrapper.find('button[aria-expanded]').exists()).toBe(true)
    // Step 1/2 always show; 3/4 (Prüfen/Export) only once generation has completed, covered below.
    expect(wrapper.findAll('.overview-section-eyebrow').map((eyebrow) => eyebrow.text())).toEqual([
      messages.step.replace('{number}', '1'),
      messages.step.replace('{number}', '2'),
    ])
  })

  it('runs the full guided flow: generate sets the working aggregation and unlocks review and export', async () => {
    stubEventSource()
    const table = routesFor(null)
    let runCreated = false
    let executionsDispatched = false
    let aggregationCreated = false
    const client = createApiClient({
      fetch: async (request) => {
        const url = new URL(request.url)
        const path = url.pathname
        if (path === `/api/v1/projects/${PROJECT_ID}`) {
          return jsonResponse(project(table.working))
        }
        if (path === '/api/v1/runs' && request.method === 'POST') {
          runCreated = true
          return jsonResponse({ id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID, status: 'created' })
        }
        if (path === `/api/v1/runs/${RUN_ID}/executions` && request.method === 'POST') {
          executionsDispatched = true
          return jsonResponse({ id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID, status: 'completed' })
        }
        if (path === `/api/v1/runs/${RUN_ID}/aggregations` && request.method === 'POST') {
          aggregationCreated = true
          return jsonResponse(AGGREGATION, { status: 201 })
        }
        if (path === `/api/v1/projects/${PROJECT_ID}/working-aggregation` && request.method === 'PUT') {
          const body = JSON.parse(await request.clone().text()) as { aggregation_execution_id: string | null }
          table.working = body.aggregation_execution_id
          return jsonResponse(project(table.working))
        }
        const route = table.get(path)
        return jsonResponse(route ?? {}, { status: route === undefined ? 404 : 200 })
      },
    })
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/gender-tagging`,
      locale,
      client,
    )
    await waitFor(() => expect(wrapper.get('h1').text()).toBe('Gender Project'))
    await waitFor(() => {
      const button = wrapper.findAll('button').find((item) => item.text() === messages.generate.title)
      expect(button).toBeDefined()
      expect(button?.attributes('disabled')).toBeUndefined()
    })
    const generate = wrapper
      .findAll('button')
      .find((button) => button.text() === messages.generate.title)
    expect(generate).toBeDefined()
    await generate!.trigger('click')
    await waitFor(() => expect(runCreated).toBe(true))
    await waitFor(() => expect(executionsDispatched).toBe(true))
    await waitFor(() => expect(aggregationCreated).toBe(true))
    await waitFor(() => expect(table.working).toBe(AGGREGATION_ID))
    await flushPromises()

    await waitFor(() =>
      expect(wrapper.findAll('h2').map((heading) => heading.text())).toContain(
        messages.review.title,
      ),
    )
    expect(wrapper.text()).toContain(messages.export.title)
    const reviewLink = wrapper.find(`a[href="/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGGREGATION_ID}/review"]`)
    expect(reviewLink.exists()).toBe(true)
    expect(wrapper.findAll('.overview-section-eyebrow').map((eyebrow) => eyebrow.text())).toEqual([
      messages.step.replace('{number}', '1'),
      messages.step.replace('{number}', '2'),
      messages.step.replace('{number}', '3'),
      messages.step.replace('{number}', '4'),
    ])
  })

  it('submits a format-only export and navigates to the export detail page', async () => {
    stubEventSource()
    const table = routesFor(AGGREGATION_ID)
    let exportBody: Record<string, unknown> | null = null
    const client = createApiClient({
      fetch: async (request) => {
        const path = new URL(request.url).pathname
        if (path === `/api/v1/projects/${PROJECT_ID}`) return jsonResponse(project(AGGREGATION_ID))
        if (path === '/api/v1/exports' && request.method === 'POST') {
          exportBody = JSON.parse(await request.clone().text()) as Record<string, unknown>
          return jsonResponse(
            { id: EXPORT_ID, run_id: RUN_ID, aggregation_execution_id: AGGREGATION_ID, status: 'queued' },
            { status: 202 },
          )
        }
        const route = table.get(path)
        return jsonResponse(route ?? {}, { status: route === undefined ? 404 : 200 })
      },
    })
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/gender-tagging`,
      locale,
      client,
    )
    await waitFor(() =>
      expect(wrapper.findAll('h2').map((heading) => heading.text())).toContain(
        messages.export.title,
      ),
    )
    const submit = wrapper
      .findAll('button')
      .find((button) => button.text() === catalogues[locale].export.new.submit)
    expect(submit).toBeDefined()
    await submit!.trigger('click')
    await waitFor(() => expect(exportBody).not.toBeNull())
    expect(exportBody).toMatchObject({
      run_id: RUN_ID,
      aggregation_execution_id: AGGREGATION_ID,
      format: 'tei',
      label_source_policy: 'machine_aggregation',
      human_resp_id: '#editor',
      tei_profile: 'tei_p5_gender_v1',
    })
    await waitFor(() =>
      expect(wrapper.vm.$route.path).toBe(
        `/projects/${PROJECT_ID}/runs/${RUN_ID}/exports/${EXPORT_ID}`,
      ),
    )
  })
})
