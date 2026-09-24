import { createHash, webcrypto } from 'node:crypto'

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
const AGG_ID = 'f0000000-0000-0000-0000-000000000001'
const EXPORT_ID = 'e2000000-0000-0000-0000-000000000001'
const NEW_EXPORT_ID = 'e2000000-0000-0000-0000-000000000002'

const OUTPUT_BYTES = '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text/></TEI>'
const OUTPUT_SHA = createHash('sha256').update(OUTPUT_BYTES).digest('hex')

function exportItem(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: EXPORT_ID,
    run_id: RUN_ID,
    aggregation_execution_id: AGG_ID,
    format: 'tei',
    label_source_policy: 'human_overrides',
    tei_profile: 'tei_p5_gender_v1',
    human_resp_id: '#editor',
    status,
    manifest_artifact_id: status === 'completed' ? 'artifact' : null,
    created_at: '2026-01-01T12:00:00Z',
    started_at: '2026-01-01T12:00:01Z',
    finished_at: status === 'completed' || status === 'failed' ? '2026-01-01T12:00:05Z' : null,
    failure_class: null,
    failure_diagnostic: null,
    ...extra,
  }
}

const MANIFEST = {
  version: 1,
  export_execution_id: EXPORT_ID,
  dataset_snapshot_id: SNAPSHOT_ID,
  source_snapshot_sha256: 'a'.repeat(64),
  run_id: RUN_ID,
  aggregation_execution_id: AGG_ID,
  format: 'tei',
  label_source_policy: 'human_overrides',
  tei_profile: 'tei_p5_gender_v1',
  outputs: [
    {
      logical_name: 'persons-a.xml',
      sha256: 'b'.repeat(64),
      byte_size: 120,
      media_type: 'application/tei+xml',
    },
    {
      logical_name: 'persons-b.xml',
      sha256: 'c'.repeat(64),
      byte_size: 98,
      media_type: 'application/tei+xml',
    },
  ],
  generated_at: '2026-01-01T12:00:05Z',
}

interface Server {
  role: 'operator' | 'viewer'
  exports: ReturnType<typeof exportItem>[]
  detail: ReturnType<typeof exportItem>
  createStatus: 202 | 409
  posts: Record<string, unknown>[]
  snapshotConfig: { source_format: string; packaging: string }
  download: { status: number; body: string; type: string }
  aggregations: boolean
}

function newServer(overrides: Partial<Server> = {}): Server {
  return {
    role: 'operator',
    exports: [],
    detail: exportItem('completed'),
    createStatus: 202,
    posts: [],
    snapshotConfig: { source_format: 'tei', packaging: 'single' },
    download: { status: 200, body: OUTPUT_BYTES, type: 'application/tei+xml' },
    aggregations: true,
    ...overrides,
  }
}

function exportClient(server: Server) {
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
          status: 'completed',
          created_at: '2026-01-01T10:00:00Z',
          config_sha256: 'e'.repeat(64),
          resolved_config: { methods: [] },
          progress: { completed: 1, failed: 0, total: 1, percentage: 100 },
          application_version: '1',
          code_git_commit: 'abc',
          python_version: '3.12',
        })
      }
      if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}`) {
        return jsonResponse({
          id: SNAPSHOT_ID,
          project_id: PROJECT_ID,
          source_artifact_id: 'a',
          source_sha256: 'a'.repeat(64),
          parser_version: '1',
          status: 'ready',
          record_count: 3,
          created_at: '2026-01-01T00:00:00Z',
          import_config: server.snapshotConfig,
        })
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/aggregations`) {
        return jsonResponse({
          items: server.aggregations
            ? [
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
              ]
            : [],
          next_cursor: null,
          has_more: false,
        })
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/exports`) {
        return jsonResponse({ items: server.exports, next_cursor: null, has_more: false })
      }
      if (pathname === '/api/v1/exports' && request.method === 'POST') {
        server.posts.push((await request.json()) as Record<string, unknown>)
        if (server.createStatus === 409) {
          return jsonResponse(
            { error: { code: 'resource_conflict', message: 'no', details: {}, request_id: 'r' } },
            { status: 409 },
          )
        }
        return jsonResponse(exportItem('queued', { id: NEW_EXPORT_ID, finished_at: null }), {
          status: 202,
        })
      }
      if (
        pathname === `/api/v1/exports/${EXPORT_ID}` ||
        pathname === `/api/v1/exports/${NEW_EXPORT_ID}`
      ) {
        return jsonResponse(server.detail)
      }
      if (pathname === `/api/v1/exports/${EXPORT_ID}/download`) {
        if (server.download.status !== 200) {
          return jsonResponse(
            { error: { code: 'resource_not_found', message: 'no', details: {}, request_id: 'r' } },
            { status: server.download.status },
          )
        }
        return new Response(server.download.body, {
          headers: { 'content-type': server.download.type },
        })
      }
      return jsonResponse({}, { status: 404 })
    },
  })
}

// jsdom has no Web Crypto subtle API, object URLs or a clickable download anchor.
const saved: { name: string }[] = []
beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  URL.createObjectURL = () => 'blob:test'
  URL.revokeObjectURL = () => {}
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push({ name: this.download })
  })
  saved.length = 0
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('exports in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].export
  const list = `/projects/${PROJECT_ID}/runs/${RUN_ID}/exports`
  const detail = `${list}/${EXPORT_ID}`

  async function mountList(server: Server) {
    const wrapper = await mountApplicationAt(list, locale, exportClient(server))
    await waitFor(() => expect(wrapper.find('.export-list').exists()).toBe(true))
    await waitFor(() => expect(wrapper.find('.export-list-empty, .export').exists()).toBe(true))
    await flushPromises()
    return wrapper
  }

  async function mountDetail(server: Server) {
    const wrapper = await mountApplicationAt(detail, locale, exportClient(server))
    await waitFor(() => expect(wrapper.find('.export-detail-title').exists()).toBe(true))
    return wrapper
  }

  it('lists a run’s exports with format, exported label and a link', async () => {
    const wrapper = await mountList(newServer({ exports: [exportItem('completed')] }))

    const item = wrapper.get('.export')
    expect(item.text()).toContain('tei')
    expect(item.text()).toContain('human_overrides')
    expect(item.get('.export-open').attributes('href')).toBe(detail)
  })

  it('offers the form only to operators, and needs a completed aggregation', async () => {
    const viewer = await mountList(newServer({ role: 'viewer' }))
    expect(viewer.find('.new-export').exists()).toBe(false)
    expect(viewer.get('.export-list-forbidden').text()).toBe(messages.forbidden)
    document.body.replaceChildren()

    const none = await mountList(newServer({ aggregations: false }))
    await waitFor(() => expect(none.find('.new-export-hint').exists()).toBe(true))
    expect(none.get('.new-export-hint').text()).toBe(messages.new.noAggregation)
    expect(none.find('.new-export-submit').exists()).toBe(false)
  })

  it('starts a TEI export with human overrides, the profile and the responsibility statement', async () => {
    const server = newServer()
    const wrapper = await mountList(server)
    await waitFor(() => expect(wrapper.find('#export-policy-human').exists()).toBe(true))

    await wrapper.get('#export-policy-human').setValue(true)
    await wrapper.get('#export-resp').setValue('#reviewer-1')
    await wrapper.get('.new-export').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))

    expect(server.posts[0]).toEqual({
      run_id: RUN_ID,
      aggregation_execution_id: AGG_ID,
      format: 'tei',
      label_source_policy: 'human_overrides',
      tei_profile: 'tei_p5_gender_v1',
      human_resp_id: '#reviewer-1',
    })
    await waitFor(() => expect(wrapper.find('.export-detail-title').exists()).toBe(true))
  })

  it('sends no TEI profile for JSON or CSV, and hides the TEI-only fields', async () => {
    const server = newServer()
    const wrapper = await mountList(server)
    await waitFor(() => expect(wrapper.find('#export-format-json').exists()).toBe(true))

    await wrapper.get('#export-format-json').setValue(true)
    expect(wrapper.find('#export-resp').exists()).toBe(false)
    await wrapper.get('.new-export').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))

    expect(server.posts[0]).toMatchObject({
      format: 'json',
      label_source_policy: 'machine_aggregation',
      human_resp_id: '#editor',
    })
    expect(server.posts[0]).not.toHaveProperty('tei_profile')
  })

  it('refuses a responsibility statement the server would refuse', async () => {
    const server = newServer()
    const wrapper = await mountList(server)
    await waitFor(() => expect(wrapper.find('#export-resp').exists()).toBe(true))

    await wrapper.get('#export-resp').setValue('editor with spaces')

    expect(wrapper.get('#export-resp').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('.new-export-submit').attributes('disabled')).toBeDefined()
    await wrapper.get('.new-export').trigger('submit')
    await flushPromises()
    expect(server.posts).toHaveLength(0)
  })

  it('explains that TEI needs a snapshot that is still TEI files, and still allows the others', async () => {
    const server = newServer({ snapshotConfig: { source_format: 'csv', packaging: 'single' } })
    const wrapper = await mountList(server)
    await waitFor(() => expect(wrapper.find('.new-export-error').exists()).toBe(true))

    expect(wrapper.get('.new-export-error').text()).toBe(messages.new.teiNotPossible)
    expect(wrapper.get('.new-export-submit').attributes('disabled')).toBeDefined()
    await wrapper.get('#export-format-csv').setValue(true)
    expect(wrapper.find('.new-export-error').exists()).toBe(false)
    expect(wrapper.get('.new-export-submit').attributes('disabled')).toBeUndefined()
  })

  it('shows what the server refused', async () => {
    const wrapper = await mountList(newServer({ createStatus: 409 }))
    await waitFor(() => expect(wrapper.find('.new-export-submit').exists()).toBe(true))

    await wrapper.get('.new-export').trigger('submit')
    await waitFor(() => expect(wrapper.find('.new-export-error').exists()).toBe(true))

    expect(wrapper.get('.new-export-error').text()).toBe(messages.new.errors.conflict)
  })

  it('downloads the output, names the file, and shows the checksum of exactly those bytes', async () => {
    const wrapper = await mountDetail(newServer())
    await waitFor(() => expect(wrapper.find('.export-detail-download').exists()).toBe(true))

    await wrapper.get('.export-detail-download').trigger('click')
    await waitFor(() => expect(wrapper.find('.export-detail-result').exists()).toBe(true))

    expect(wrapper.get('.export-detail-result .export-detail-hash').text()).toBe(OUTPUT_SHA)
    expect(wrapper.get('.export-detail-result').text()).toContain('export-')
    expect(saved).toHaveLength(1)
    expect(saved[0]?.name).toMatch(/\.xml$/)
    // A single output has no manifest in the API: the reader is told where to compare.
    expect(wrapper.get('.export-detail-result').text()).toContain(
      messages.detail.manifestNotExposed,
    )
  })

  it('verifies a pasted manifest checksum: match, mismatch, and not a checksum', async () => {
    const wrapper = await mountDetail(newServer())
    await waitFor(() => expect(wrapper.find('.export-detail-download').exists()).toBe(true))
    await wrapper.get('.export-detail-download').trigger('click')
    await waitFor(() => expect(wrapper.find('#export-expected').exists()).toBe(true))

    await wrapper.get('#export-expected').setValue(`  ${OUTPUT_SHA.toUpperCase()}  `)
    expect(wrapper.get('.export-detail-verdict').text()).toBe(messages.detail.verdict.match)

    await wrapper.get('#export-expected').setValue('0'.repeat(64))
    expect(wrapper.get('.export-detail-verdict').text()).toBe(messages.detail.verdict.mismatch)

    await wrapper.get('#export-expected').setValue('not a checksum')
    expect(wrapper.get('.export-detail-verdict').text()).toBe(messages.detail.verdict.malformed)

    await wrapper.get('#export-expected').setValue('')
    expect(wrapper.get('.export-detail-verdict').text()).toBe('')
  })

  it('lists the manifest’s outputs and the source snapshot when the server answers with the manifest', async () => {
    const server = newServer({
      download: { status: 200, body: JSON.stringify(MANIFEST), type: 'application/json' },
    })
    const wrapper = await mountDetail(server)
    await waitFor(() => expect(wrapper.find('.export-detail-download').exists()).toBe(true))
    await wrapper.get('.export-detail-download').trigger('click')
    await waitFor(() => expect(wrapper.find('.export-detail-manifest').exists()).toBe(true))

    const manifest = wrapper.get('.export-detail-manifest')
    expect(manifest.text()).toContain(messages.detail.manifestReceived)
    expect(manifest.text()).toContain('a'.repeat(64))
    const rows = manifest.findAll('tbody tr').map((row) => row.text())
    expect(rows[0]).toContain('persons-a.xml')
    expect(rows[0]).toContain('b'.repeat(64))
    expect(rows[1]).toContain('persons-b.xml')
    expect(saved[0]?.name).toBe('manifest.json')
  })

  it('does not mistake a JSON result bundle for a manifest', async () => {
    const server = newServer({
      detail: exportItem('completed', { format: 'json', tei_profile: null }),
      download: {
        status: 200,
        body: JSON.stringify([{ tei_id: 'demo-1' }]),
        type: 'application/json',
      },
    })
    const wrapper = await mountDetail(server)
    await waitFor(() => expect(wrapper.find('.export-detail-download').exists()).toBe(true))
    await wrapper.get('.export-detail-download').trigger('click')
    await waitFor(() => expect(wrapper.find('.export-detail-result').exists()).toBe(true))

    expect(wrapper.find('.export-detail-manifest').exists()).toBe(false)
    expect(saved[0]?.name).toMatch(/\.json$/)
  })

  it('says so when there is nothing to download', async () => {
    const wrapper = await mountDetail(
      newServer({ download: { status: 404, body: '', type: 'application/json' } }),
    )
    await waitFor(() => expect(wrapper.find('.export-detail-download').exists()).toBe(true))

    await wrapper.get('.export-detail-download').trigger('click')
    await waitFor(() => expect(wrapper.find('.export-detail-error').exists()).toBe(true))

    expect(wrapper.get('.export-detail-error').text()).toBe(messages.detail.errors.notFound)
    expect(wrapper.find('.export-detail-result').exists()).toBe(false)
  })

  it('waits for a running export and shows why a failed one failed', async () => {
    const running = await mountDetail(
      newServer({ detail: exportItem('running', { finished_at: null }) }),
    )
    expect(running.get('.export-detail-waiting').text()).toBe(messages.detail.waiting)
    expect(running.find('.export-detail-download').exists()).toBe(false)
    document.body.replaceChildren()

    const failed = await mountDetail(
      newServer({
        detail: exportItem('failed', {
          failure_class: 'ExportError',
          failure_diagnostic: 'a tabular snapshot cannot be exported as TEI',
        }),
      }),
    )
    expect(failed.get('.export-detail-failure-class').text()).toBe('ExportError')
    expect(failed.get('.export-detail-failure').text()).toContain('tabular snapshot')
    expect(failed.find('.export-detail-download').exists()).toBe(false)
  })
})
