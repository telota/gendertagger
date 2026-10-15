import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

// jsdom's own `File` cannot be read by Vitest's Node-`fetch`-compat layer when it ends up inside a
// `FormData` body (see tests/features/projects/import.spec.ts for the same workaround).
import { File as NodeFile } from 'node:buffer'
import { enableAutoUnmount, flushPromises, type VueWrapper } from '@vue/test-utils'
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

function testFile(content: string, name: string, type: string): File {
  return new NodeFile([content], name, { type }) as unknown as File
}

function selectFile(wrapper: VueWrapper, selector: string, file: File): void {
  const input = wrapper.get(selector).element as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  input.dispatchEvent(new Event('change'))
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

  it('unlocks Schritt 2 as soon as a new import finishes, without a reload, and hides the advanced-only post-import actions (bugfix)', async () => {
    stubEventSource()
    const table = routesFor(null)
    const newSnapshotId = 'c0000000-0000-0000-0000-000000000002'
    let statusQueried = false
    const client = createApiClient({
      fetch: async (request) => {
        const path = new URL(request.url).pathname
        if (path === `/api/v1/projects/${PROJECT_ID}`) return jsonResponse(project(null))
        if (path === `/api/v1/projects/${PROJECT_ID}/snapshots` && request.method === 'POST') {
          return jsonResponse(
            {
              id: newSnapshotId,
              project_id: PROJECT_ID,
              status: 'pending',
              created_at: '2026-01-02T00:00:00Z',
            },
            { status: 202 },
          )
        }
        if (path === `/api/v1/snapshots/${newSnapshotId}`) {
          statusQueried = true
          return jsonResponse({
            id: newSnapshotId,
            project_id: PROJECT_ID,
            status: 'ready',
            record_count: 7,
            created_at: '2026-01-02T00:00:00Z',
            ready_at: '2026-01-02T00:05:00Z',
            parser_version: 1,
            source_sha256: 'z'.repeat(64),
            import_config: { source_format: 'csv', packaging: 'single' },
            failure_diagnostic: null,
          })
        }
        if (path === `/api/v1/projects/${PROJECT_ID}/snapshots`) {
          // The list only ever reflects the new import once its own status poll has resolved —
          // exactly the gap the fix closes: without it, nothing refetches this list again after
          // the one-time invalidation at upload time, which happens while still pending.
          return jsonResponse(
            statusQueried
              ? {
                  items: [{ ...READY_SNAPSHOT, id: newSnapshotId, record_count: 7 }],
                  has_more: false,
                  next_cursor: null,
                }
              : { items: [], has_more: false, next_cursor: null },
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
    await waitFor(() => expect(wrapper.get('h1').text()).toBe('Gender Project'))
    await wrapper.get('main button[aria-expanded]').trigger('click')
    await flushPromises()

    selectFile(
      wrapper,
      '.import-file-input',
      testFile(
        'xml:id,persName,birth,death,event,note,idno\nS1,[],,,[],,[]\n',
        'source.csv',
        'text/csv',
      ),
    )
    await waitFor(() =>
      expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(false),
    )
    await wrapper.get('form').trigger('submit')

    await waitFor(() => {
      const button = wrapper
        .findAll('button')
        .find((item) => item.text() === messages.generate.title)
      expect(button).toBeDefined()
      expect(button?.attributes('disabled')).toBeUndefined()
    })
    expect(wrapper.find('.import-status-data-link').exists()).toBe(false)
    expect(wrapper.find('.import-another').exists()).toBe(false)
  })

  it('resets to "not generated yet" once a newer dataset supersedes the working aggregation (bugfix)', async () => {
    stubEventSource()
    const newSnapshotId = 'c0000000-0000-0000-0000-000000000002'
    const newReadySnapshot = {
      ...READY_SNAPSHOT,
      id: newSnapshotId,
      record_count: 9,
      created_at: '2026-02-01T00:00:00Z',
    }
    const table = routesFor(AGGREGATION_ID)
    const client = createApiClient({
      fetch: (request) => {
        const path = new URL(request.url).pathname
        if (path === `/api/v1/projects/${PROJECT_ID}`) {
          return Promise.resolve(jsonResponse(project(AGGREGATION_ID)))
        }
        if (path === `/api/v1/projects/${PROJECT_ID}/snapshots`) {
          // Newest first, matching the real list order: the working aggregation's own run (mocked
          // below) still points at the *older* snapshot, so it no longer reflects Schritt 1's
          // current dataset.
          return Promise.resolve(
            jsonResponse({
              items: [newReadySnapshot, READY_SNAPSHOT],
              has_more: false,
              next_cursor: null,
            }),
          )
        }
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

    await waitFor(() => {
      const button = wrapper
        .findAll('button')
        .find((item) => item.text() === messages.generate.title)
      expect(button).toBeDefined()
    })
    // Schritt 3/4 (Prüfen/Export) only ever show once `isDone`; staleness must keep them hidden.
    expect(wrapper.findAll('h2').map((heading) => heading.text())).not.toContain(
      messages.review.title,
    )
    expect(wrapper.findAll('h2').map((heading) => heading.text())).not.toContain(
      messages.export.title,
    )
    expect(wrapper.findAll('.overview-section-eyebrow').map((eyebrow) => eyebrow.text())).toEqual([
      messages.step.replace('{number}', '1'),
      messages.step.replace('{number}', '2'),
    ])
  })

  it('names the real reason when the reference strategy rejects the method selection (bugfix)', async () => {
    stubEventSource()
    const table = routesFor(null)
    const client = createApiClient({
      fetch: async (request) => {
        const path = new URL(request.url).pathname
        if (path === `/api/v1/projects/${PROJECT_ID}`) return jsonResponse(project(null))
        if (path === '/api/v1/runs' && request.method === 'POST') {
          return jsonResponse({ id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID, status: 'created' })
        }
        if (path === `/api/v1/runs/${RUN_ID}/executions` && request.method === 'POST') {
          return jsonResponse({ id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID, status: 'completed' })
        }
        if (path === `/api/v1/runs/${RUN_ID}/aggregations` && request.method === 'POST') {
          return jsonResponse(
            {
              error: {
                code: 'resource_conflict',
                message: 'The method execution selection is not aggregatable.',
                details: {},
              },
            },
            { status: 409 },
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
    await waitFor(() => expect(wrapper.get('h1').text()).toBe('Gender Project'))
    await waitFor(() => {
      const button = wrapper.findAll('button').find((item) => item.text() === messages.generate.title)
      expect(button?.attributes('disabled')).toBeUndefined()
    })
    const generate = wrapper
      .findAll('button')
      .find((button) => button.text() === messages.generate.title)
    await generate!.trigger('click')

    await waitFor(() =>
      expect(wrapper.text()).toContain(catalogues[locale].aggregations.errors.autoNotAggregatable),
    )
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

  it('picks up a run that already finished without this page watching it, instead of orphaning it (bugfix)', async () => {
    stubEventSource()
    const table = routesFor(null)
    let aggregationCreated = false
    const client = createApiClient({
      fetch: async (request) => {
        const path = new URL(request.url).pathname
        if (path === `/api/v1/projects/${PROJECT_ID}`) return jsonResponse(project(table.working))
        if (path === `/api/v1/snapshots/${SNAPSHOT_ID}/runs`) {
          // A run this page never saw created (e.g. a reload mid-generation, found the hard way):
          // it finished successfully in the background, but nothing here ever watched it happen.
          return jsonResponse({
            items: [{ id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID, status: 'completed', created_at: '2026-01-01T00:10:00Z' }],
            has_more: false,
            next_cursor: null,
          })
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

    await waitFor(() => expect(aggregationCreated).toBe(true))
    await waitFor(() => expect(table.working).toBe(AGGREGATION_ID))
    await waitFor(() =>
      expect(wrapper.findAll('h2').map((heading) => heading.text())).toContain(
        messages.review.title,
      ),
    )
  })

  it('retries without a method the deployment cannot run yet, instead of failing outright (bugfix)', async () => {
    stubEventSource()
    const table = routesFor(null)
    const runRequestBodies: Array<{ name: string }[]> = []
    const client = createApiClient({
      fetch: async (request) => {
        const path = new URL(request.url).pathname
        if (path === `/api/v1/projects/${PROJECT_ID}`) return jsonResponse(project(table.working))
        if (path === '/api/v1/methods') {
          return jsonResponse([
            { name: 'method-a', implementation_version: '1', method_confidence_range: [0, 1] },
            { name: 'gnd', implementation_version: '1', method_confidence_range: null },
          ])
        }
        if (path === '/api/v1/runs' && request.method === 'POST') {
          const body = (await request.clone().json()) as { config: { methods: { name: string }[] } }
          runRequestBodies.push(body.config.methods)
          if (body.config.methods.some((method) => method.name === 'gnd')) {
            return jsonResponse(
              {
                error: {
                  code: 'validation_error',
                  message: 'The run configuration is invalid.',
                  details: { reason: "configuration for method 'gnd' is invalid" },
                },
              },
              { status: 422 },
            )
          }
          return jsonResponse({ id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID, status: 'created' })
        }
        if (path === `/api/v1/runs/${RUN_ID}/executions` && request.method === 'POST') {
          return jsonResponse({ id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID, status: 'completed' })
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
    await generate!.trigger('click')

    await waitFor(() => expect(runRequestBodies.length).toBe(2))
    expect(runRequestBodies[0]?.map((method) => method.name)).toEqual(['method-a', 'gnd'])
    expect(runRequestBodies[1]?.map((method) => method.name)).toEqual(['method-a'])
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
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
