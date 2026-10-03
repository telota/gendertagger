import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore } from '@/stores/session'

import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const
const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Operator', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const CHECKSUM = 'ab'.repeat(32)
const listPath = `/projects/${PROJECT_ID}/snapshots`

function snapshot(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    project_id: PROJECT_ID,
    source_artifact_id: 'd0000000-0000-0000-0000-000000000001',
    source_sha256: CHECKSUM,
    parser_version: 'parser-7',
    import_config: { source_format: 'tei' },
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
  import_config: { source_format: 'csv' },
  failure_diagnostic: 'Unrecognised encoding.',
})
function page(items: unknown[], next: string | null = null) {
  return Response.json({ items, has_more: next !== null, next_cursor: next })
}
function failure(status = 503) {
  return Response.json({ error: { code: 'internal_error', message: 'Unavailable.' } }, { status })
}
function deferred() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}
type Handler = (request: Request) => Response | Promise<Response> | undefined
function client(extra: Handler, role = 'operator', mustChangePassword = false) {
  return createApiClient({
    fetch: async (request) => {
      const handled = await extra(request)
      if (handled) return handled
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/branding') return Response.json({})
      if (pathname === '/api/v1/me') return Response.json(USER)
      if (pathname === '/api/v1/auth/session')
        return Response.json({ must_change_password: mustChangePassword, keep_signed_in: false })
      if (pathname === `/api/v1/projects/${PROJECT_ID}`)
        return Response.json({
          id: PROJECT_ID,
          slug: 'project-a',
          display_name: 'Project A',
          description: null,
          current_user_role: role,
          created_at: '2026-01-01T00:00:00Z',
        })
      return Response.json({}, { status: 404 })
    },
  })
}
const isListRequest = (request: Request) =>
  new URL(request.url).pathname === `/api/v1/projects/${PROJECT_ID}/snapshots`
enableAutoUnmount(afterEach)
afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('imported data list in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].data
  const statuses = catalogues[locale].projects.snapshots

  it('shows dated snapshot cards and links to their detail without requesting provenance', async () => {
    const paths: string[] = []
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client((request) => {
        paths.push(new URL(request.url).pathname)
        return isListRequest(request) ? page([SNAPSHOT_A, SNAPSHOT_B]) : undefined
      }),
    )
    await waitFor(() => expect(wrapper.findAll('.snapshot')).toHaveLength(2))
    expect(wrapper.findAll('main h1')).toHaveLength(1)
    expect(wrapper.get('main h1').text()).toBe(messages.title)
    const items = wrapper.findAll('.snapshot')
    expect(items[0]?.text()).toContain(statuses.status.ready)
    expect(items[0]?.text()).toContain('TEI')
    expect(items[0]?.text()).toMatch(/1[.,]234/)
    expect(items[0]?.get('.snapshot-title').text()).toContain('2026')
    expect(items[0]?.text()).not.toContain('parser-7')
    expect(items[0]?.text()).not.toContain(CHECKSUM)
    expect(items[1]?.text()).toContain(statuses.status.failed)
    expect(items[1]?.text()).toContain('Unrecognised encoding.')
    expect(items[1]?.text()).not.toContain(statuses.recordCount)
    for (const [index, value] of [SNAPSHOT_A, SNAPSHOT_B].entries()) {
      expect(items[index]?.get('.snapshot-open').attributes('href')).toBe(`${listPath}/${value.id}`)
    }
    expect(paths.some((path) => path.endsWith('/source-members'))).toBe(false)
    expect(paths).not.toContain('/api/v1/snapshot-upload-limits')
    expect(wrapper.find('.project-snapshots-import').exists()).toBe(false)
    expect(wrapper.find('.import-file-input').exists()).toBe(false)
    await expectNoAxeViolations(wrapper.get('main').element)
  })

  it('shows only a verified source format and retains every lifecycle state', async () => {
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client((request) =>
        isListRequest(request)
          ? page([
              snapshot('pending', {
                status: 'pending',
                record_count: null,
                import_config: { source_format: '<invalid>' },
              }),
              snapshot('importing', {
                status: 'importing',
                record_count: null,
                import_config: { source_format: ['tei'] },
              }),
            ])
          : undefined,
      ),
    )
    await waitFor(() => expect(wrapper.findAll('.snapshot')).toHaveLength(2))
    expect(wrapper.get('main').text()).toContain(statuses.status.pending)
    expect(wrapper.get('main').text()).toContain(statuses.status.importing)
    expect(wrapper.get('main').text()).not.toContain(messages.sourceFormat)
    expect(wrapper.get('main').text()).not.toContain('<invalid>')
    expect(wrapper.findAll('.snapshot-open')).toHaveLength(2)
  })

  it('provides the empty explanation regardless of role, with no import control on this page', async () => {
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client((request) => (isListRequest(request) ? page([]) : undefined), 'viewer'),
    )
    await waitFor(() => expect(wrapper.get('main').text()).toContain(messages.empty))
    expect(wrapper.get('main').text()).toContain(messages.emptyHint)
    expect(wrapper.find('.project-snapshots-import').exists()).toBe(false)
    expect(wrapper.find('.snapshot-import-form').exists()).toBe(false)
  })

  it('waits for project access and retains its H1 while loading', async () => {
    const pending = deferred()
    let lists = 0
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client((request) => {
        if (new URL(request.url).pathname === `/api/v1/projects/${PROJECT_ID}`)
          return pending.promise
        if (isListRequest(request)) {
          lists += 1
          return page([])
        }
        return undefined
      }),
    )
    expect(wrapper.get('main h1').text()).toBe(messages.title)
    expect(wrapper.get('main [role="status"]').text()).toBe(messages.loading)
    expect(wrapper.get('.project-snapshots > .app-feedback').classes()).toContain('app-card')
    expect(lists).toBe(0)
    expect(wrapper.find('.project-snapshots-import').exists()).toBe(false)
    pending.resolve(failure(403))
    await waitFor(() =>
      expect(wrapper.get('main [role="alert"]').text()).toBe(messages.accessUnavailable),
    )
    expect(wrapper.get('.project-snapshots > .app-feedback').classes()).toContain('app-card')
    expect(lists).toBe(0)
  })

  it('distinguishes list loading, failure, and an empty successful retry', async () => {
    const pending = deferred()
    let calls = 0
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client((request) => {
        if (!isListRequest(request)) return undefined
        calls += 1
        return calls === 1 ? pending.promise : page([])
      }),
    )
    await waitFor(() => expect(wrapper.find('.snapshot-list-skeleton').exists()).toBe(true))
    expect(wrapper.get('.snapshot-list > .app-feedback').classes()).toContain('app-card')
    expect(wrapper.findAll('.snapshot-skeleton')).toHaveLength(3)
    for (const skeleton of wrapper.findAll('.snapshot-skeleton')) {
      expect(skeleton.classes()).toContain('app-resource-card')
    }
    expect(wrapper.get('main').text()).not.toContain(messages.empty)
    pending.resolve(failure())
    await waitFor(() => expect(wrapper.get('main [role="alert"]').text()).toBe(messages.loadError))
    expect(wrapper.get('main').text()).not.toContain(messages.empty)
    await wrapper.get('.snapshot-list-retry').trigger('click')
    await waitFor(() => expect(wrapper.get('main').text()).toContain(messages.empty))
  })

  it('retains loaded rows through a busy next page, failure, and retry using the same cursor', async () => {
    const pending = deferred()
    const cursors: (string | null)[] = []
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client((request) => {
        if (!isListRequest(request)) return undefined
        const cursor = new URL(request.url).searchParams.get('cursor')
        cursors.push(cursor)
        if (cursor === null) return page([SNAPSHOT_A], 'next')
        return cursors.length === 2 ? pending.promise : page([SNAPSHOT_B])
      }),
    )
    await waitFor(() => expect(wrapper.findAll('.snapshot')).toHaveLength(1))
    await wrapper.get('.snapshot-list-load-more').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLButtonElement>('.snapshot-list-load-more').element.disabled).toBe(true)
    expect(wrapper.get('main [role="status"]').text()).toBe(messages.loadingMore)
    expect(wrapper.get('.snapshot-list-feedback').classes()).toContain('app-card')
    expect(wrapper.findAll('.snapshot')).toHaveLength(1)
    pending.resolve(failure())
    await waitFor(() =>
      expect(wrapper.get('main [role="alert"]').text()).toBe(messages.loadMoreError),
    )
    expect(wrapper.get('.snapshot-list-feedback').classes()).toContain('app-card')
    expect(wrapper.findAll('.snapshot')).toHaveLength(1)
    expect(wrapper.get('.snapshot-list-load-more').text()).toBe(catalogues[locale].projects.retry)
    await wrapper.get('.snapshot-list-load-more').trigger('click')
    await waitFor(() => expect(wrapper.findAll('.snapshot')).toHaveLength(2))
    expect(cursors).toEqual([null, 'next', 'next'])
    expect(wrapper.find('.snapshot-list-load-more').exists()).toBe(false)
  })

  it('preserves newest import first and the server tie order across cursor pages', async () => {
    const newest = snapshot('c0000000-0000-0000-0000-000000000001', {
      created_at: '2026-03-04T10:15:00Z',
      ready_at: '2026-03-04T10:16:00Z',
    })
    const tiedHigher = snapshot('c0000000-0000-0000-0000-000000000003', {
      created_at: '2026-03-03T10:15:00Z',
      ready_at: '2026-03-04T10:17:00Z',
    })
    const tiedLower = snapshot('c0000000-0000-0000-0000-000000000002', {
      created_at: '2026-03-03T10:15:00Z',
      ready_at: '2026-03-04T10:18:00Z',
    })
    const oldest = snapshot('c0000000-0000-0000-0000-000000000004', {
      created_at: '2026-03-02T10:15:00Z',
      ready_at: '2026-03-04T10:19:00Z',
    })
    const cursors: (string | null)[] = []
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client((request) => {
        if (!isListRequest(request)) return undefined
        const cursor = new URL(request.url).searchParams.get('cursor')
        cursors.push(cursor)
        return cursor === null ? page([newest, tiedHigher], 'next') : page([tiedLower, oldest])
      }),
    )
    await waitFor(() => expect(wrapper.findAll('.snapshot')).toHaveLength(2))
    await wrapper.get('.snapshot-list-load-more').trigger('click')
    await waitFor(() => expect(wrapper.findAll('.snapshot')).toHaveLength(4))

    expect(wrapper.findAll('.snapshot-title-link').map((link) => link.attributes('href'))).toEqual(
      [newest, tiedHigher, tiedLower, oldest].map((item) => `${listPath}/${item.id}`),
    )
    expect(cursors).toEqual([null, 'next'])
    expect(wrapper.find('.snapshot-list-load-more').exists()).toBe(false)
  })

  it('hides loaded rows when a later request reports lost access', async () => {
    let calls = 0
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client((request) => {
        if (!isListRequest(request)) return undefined
        calls += 1
        return calls === 1 ? page([SNAPSHOT_A], 'next') : failure(403)
      }),
    )
    await waitFor(() => expect(wrapper.findAll('.snapshot')).toHaveLength(1))
    await wrapper.get('.snapshot-list-load-more').trigger('click')
    await waitFor(() =>
      expect(wrapper.get('main [role="alert"]').text()).toBe(messages.accessUnavailable),
    )
    expect(wrapper.findAll('.snapshot')).toHaveLength(0)
  })

  it('removes snapshot and import controls immediately when the session is no longer eligible', async () => {
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client((request) => (isListRequest(request) ? page([SNAPSHOT_A]) : undefined)),
    )
    await waitFor(() => expect(wrapper.findAll('.snapshot')).toHaveLength(1))
    const session = useSessionStore()
    session.isAuthenticating = true
    await flushPromises()
    expect(wrapper.find('.snapshot-list').exists()).toBe(false)
    expect(wrapper.find('.project-snapshots-import').exists()).toBe(false)
    expect(wrapper.get('main h1').text()).toBe(messages.title)
  })

  it('redirects a user who must change their password before requesting project data', async () => {
    let projectRequests = 0
    let listRequests = 0
    const wrapper = await mountApplicationAt(
      listPath,
      locale,
      client(
        (request) => {
          const { pathname } = new URL(request.url)
          if (pathname === `/api/v1/projects/${PROJECT_ID}`) projectRequests += 1
          if (isListRequest(request)) listRequests += 1
          return undefined
        },
        'operator',
        true,
      ),
    )

    await waitFor(() => expect(wrapper.vm.$router.currentRoute.value.name).toBe('changePassword'))
    expect(wrapper.vm.$router.currentRoute.value.query.redirect).toBe(listPath)
    expect(projectRequests).toBe(0)
    expect(listRequests).toBe(0)
  })
})
