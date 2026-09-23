import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { mountApplicationAt } from '../../helpers/render'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

const catalogues = { de, en } as const

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Operator', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const CHECKSUM = 'ab'.repeat(32)
const MEMBER_CHECKSUM = 'cd'.repeat(32)

function snapshot(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    project_id: PROJECT_ID,
    source_artifact_id: 'd0000000-0000-0000-0000-000000000001',
    source_sha256: CHECKSUM,
    parser_version: 'parser-7',
    status: 'ready',
    record_count: 1234,
    created_at: '2026-03-04T10:15:00Z',
    ...overrides,
  }
}

const SNAPSHOT_A = snapshot('c0000000-0000-0000-0000-00000000000a')
const SNAPSHOT_B = snapshot('c0000000-0000-0000-0000-00000000000b', {
  status: 'failed',
  record_count: null,
  failure_diagnostic: 'Unrecognised encoding.',
})

type Handler = (request: Request) => Response | Promise<Response> | undefined

/** A client answering the shell's own requests plus whatever `extra` handles first. */
function client(extra: Handler) {
  return createApiClient({
    fetch: async (request) => {
      const handled = await extra(request)
      if (handled) return handled
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/branding') return jsonResponse({})
      if (pathname === '/api/v1/me') return jsonResponse(USER)
      if (pathname === '/api/v1/auth/session') {
        return jsonResponse({ must_change_password: false, keep_signed_in: false })
      }
      if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
        return jsonResponse({
          id: PROJECT_ID,
          slug: 'project-a',
          display_name: 'Project A',
          description: null,
          current_user_role: 'operator',
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

describe.each(['de', 'en'] as const)('snapshot list in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projects.snapshots
  const overviewPath = `/projects/${PROJECT_ID}/overview`

  function snapshotsPage(items: unknown[], hasMore = false, nextCursor: string | null = null) {
    return jsonResponse({ items, has_more: hasMore, next_cursor: nextCursor })
  }

  const isListRequest = (request: Request) =>
    new URL(request.url).pathname === `/api/v1/projects/${PROJECT_ID}/snapshots`

  it('shows each snapshot with its status, record count, parser version, and checksum', async () => {
    const wrapper = await mountApplicationAt(
      overviewPath,
      locale,
      client((request) =>
        isListRequest(request) ? snapshotsPage([SNAPSHOT_A, SNAPSHOT_B]) : undefined,
      ),
    )
    await flushPromises()

    const items = wrapper.findAll('.snapshot')
    expect(items).toHaveLength(2)
    expect(items[0]?.text()).toContain(messages.status.ready)
    expect(items[0]?.text()).toContain('parser-7')
    expect(items[0]?.text()).toContain(CHECKSUM)
    expect(items[0]?.text()).toMatch(/1[.,]234/)
    expect(items[1]?.text()).toContain(messages.status.failed)
    expect(items[1]?.text()).toContain('Unrecognised encoding.')
    expect(items[1]?.text()).not.toContain(messages.recordCount)
  })

  it('shows the empty state when nothing has been imported', async () => {
    const wrapper = await mountApplicationAt(
      overviewPath,
      locale,
      client((request) => (isListRequest(request) ? snapshotsPage([]) : undefined)),
    )
    await flushPromises()

    expect(wrapper.get('.snapshot-list').text()).toContain(messages.empty)
  })

  it('shows a load error and retries when the list fails to load', async () => {
    let calls = 0
    const wrapper = await mountApplicationAt(
      overviewPath,
      locale,
      client((request) => {
        if (!isListRequest(request)) return undefined
        calls += 1
        return calls === 1
          ? jsonResponse({ error: { code: 'internal_error', message: 'x' } }, { status: 500 })
          : snapshotsPage([SNAPSHOT_A])
      }),
    )
    await flushPromises()
    expect(wrapper.get('.snapshot-list').text()).toContain(messages.loadError)

    await wrapper.get('.snapshot-list-retry').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.snapshot')).toHaveLength(1)
  })

  it('loads the next page on request', async () => {
    let calls = 0
    const wrapper = await mountApplicationAt(
      overviewPath,
      locale,
      client((request) => {
        if (!isListRequest(request)) return undefined
        calls += 1
        return calls === 1
          ? snapshotsPage([SNAPSHOT_A], true, 'cursor-1')
          : snapshotsPage([SNAPSHOT_B])
      }),
    )
    await flushPromises()
    expect(wrapper.findAll('.snapshot')).toHaveLength(1)

    await wrapper.get('.snapshot-list-load-more').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.snapshot')).toHaveLength(2)
  })

  it('reveals the source files of a snapshot on request', async () => {
    let membersRequested = false
    const wrapper = await mountApplicationAt(
      overviewPath,
      locale,
      client((request) => {
        const { pathname } = new URL(request.url)
        if (isListRequest(request)) return snapshotsPage([SNAPSHOT_A])
        if (pathname === `/api/v1/snapshots/${SNAPSHOT_A.id}/source-members`) {
          membersRequested = true
          return jsonResponse([
            {
              id: 'e0000000-0000-0000-0000-000000000001',
              dataset_snapshot_id: SNAPSHOT_A.id,
              artifact_id: 'f0000000-0000-0000-0000-000000000001',
              logical_name: 'persons.xml',
              media_type: 'application/tei+xml',
              byte_size: 2048,
              ordinal: 0,
              sha256: MEMBER_CHECKSUM,
              created_at: '2026-03-04T10:15:00Z',
            },
          ])
        }
        return undefined
      }),
    )
    await flushPromises()
    expect(membersRequested).toBe(false)
    expect(wrapper.find('.snapshot-members').exists()).toBe(false)

    const toggle = wrapper.get('.snapshot-toggle')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    await flushPromises()

    expect(toggle.attributes('aria-expanded')).toBe('true')
    const table = wrapper.get('.snapshot-members-table')
    expect(table.text()).toContain('persons.xml')
    expect(table.text()).toContain('application/tei+xml')
    expect(table.text()).toContain(MEMBER_CHECKSUM)
    expect(toggle.text()).toBe(messages.hideMembers)

    await toggle.trigger('click')
    expect(wrapper.find('.snapshot-members').exists()).toBe(false)
  })

  it('shows an error and retries when the source files fail to load', async () => {
    let calls = 0
    const wrapper = await mountApplicationAt(
      overviewPath,
      locale,
      client((request) => {
        const { pathname } = new URL(request.url)
        if (isListRequest(request)) return snapshotsPage([SNAPSHOT_A])
        if (pathname === `/api/v1/snapshots/${SNAPSHOT_A.id}/source-members`) {
          calls += 1
          return calls === 1
            ? jsonResponse({ error: { code: 'internal_error', message: 'x' } }, { status: 500 })
            : jsonResponse([])
        }
        return undefined
      }),
    )
    await flushPromises()

    await wrapper.get('.snapshot-toggle').trigger('click')
    await flushPromises()
    expect(wrapper.get('.snapshot-members').text()).toContain(messages.membersLoadError)

    await wrapper.get('.snapshot-members-retry').trigger('click')
    await flushPromises()

    expect(wrapper.find('.snapshot-members-table').exists()).toBe(true)
  })
})
