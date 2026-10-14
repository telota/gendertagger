import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../../helpers/api'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const

const VIEWER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Viewer One', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const PROJECT = {
  id: PROJECT_ID,
  slug: 'project-a',
  display_name: 'Project A',
  description: 'The first project.',
  current_user_role: 'viewer',
  created_at: '2026-01-01T00:00:00Z',
  team: {
    id: 'c0000000-0000-0000-0000-000000000001',
    slug: 'editors',
    display_name: 'Editorial Team',
    created_at: '2026-01-01T00:00:00Z',
  },
  working_aggregation_execution_id: null,
}
const SNAPSHOT_ID = 'd0000000-0000-0000-0000-000000000001'
const RUN_ID = 'f0000000-0000-0000-0000-000000000001'
const NOT_FOUND = {
  body: { error: { code: 'resource_not_found', message: 'Gone.' } },
  init: { status: 404 },
}

function signedInRoutes(
  projectBody: RouteResponse,
  more: Record<string, RouteResponse> = {},
): Record<string, RouteResponse> {
  return {
    '/api/v1/branding': { body: {} },
    '/api/v1/me': { body: VIEWER },
    '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    [`/api/v1/projects/${PROJECT_ID}`]: projectBody,
    ...more,
  }
}

const page = (items: unknown[]): RouteResponse => ({
  body: { items, has_more: false, next_cursor: null },
})

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })

function snapshot(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: SNAPSHOT_ID,
    project_id: PROJECT_ID,
    status,
    record_count: 480,
    created_at: '2026-02-01T10:00:00Z',
    ready_at: status === 'ready' ? '2026-02-01T10:05:00Z' : null,
    ...extra,
  }
}

const fill = (message: string, values: Record<string, string | number>): string =>
  message.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key]))

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('ProjectOverviewView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projects

  it('shows the project name, slug, role, and description', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(signedInRoutes({ body: PROJECT })),
    )
    await flushPromises()

    expect(wrapper.get('main h1').text()).toBe('Project A')
    expect(wrapper.text()).toContain(PROJECT.slug)
    expect(wrapper.text()).toContain(messages.role.viewer)
    expect(wrapper.text()).toContain('The first project.')
    expect(wrapper.find('.game-mode-setting').exists()).toBe(false)
  })

  it('lets a project operator enable game mode for this project', async () => {
    let project = {
      ...PROJECT,
      current_user_role: 'operator',
      current_user_can_manage_members: true,
      manager_user_id: VIEWER.id,
      created_by_user_id: VIEWER.id,
      game_mode_enabled: false,
    }
    const writes: { enabled: boolean }[] = []
    const client = createApiClient({
      fetch: async (request) => {
        const path = new URL(request.url).pathname
        if (path === '/api/v1/branding') return json({})
        if (path === '/api/v1/me') return json(VIEWER)
        if (path === '/api/v1/auth/session') {
          return json({ must_change_password: false, keep_signed_in: false })
        }
        if (request.method === 'PUT' && path === `/api/v1/projects/${PROJECT_ID}/game-mode`) {
          const body = (await request.json()) as { enabled: boolean }
          writes.push(body)
          project = { ...project, game_mode_enabled: body.enabled }
          return json(project)
        }
        if (path === `/api/v1/projects/${PROJECT_ID}`) return json(project)
        if (path === '/api/v1/projects') return json(page([project]).body)
        if (path === `/api/v1/projects/${PROJECT_ID}/data-availability`) {
          return json({
            project_id: PROJECT_ID,
            has_ready_snapshots: false,
            has_completed_aggregations: false,
          })
        }
        if (path === `/api/v1/projects/${PROJECT_ID}/snapshots`) return json(page([]).body)
        return json({ error: { code: 'resource_not_found', message: 'Not mocked.' } }, 404)
      },
    })
    const wrapper = await mountApplicationAt(`/projects/${PROJECT_ID}/overview`, locale, client)
    const toggle = wrapper.get<HTMLInputElement>('.game-mode-setting__control input')
    expect(toggle.element.checked).toBe(false)

    await toggle.setValue(true)
    await waitFor(() => expect(writes).toEqual([{ enabled: true }]))
    await waitFor(() =>
      expect(
        wrapper.get<HTMLInputElement>('.game-mode-setting__control input').element.checked,
      ).toBe(true),
    )
    expect(wrapper.get('.game-mode-setting__status').text()).toBe(messages.overview.gameMode.saved)
  })

  it('shows a placeholder when the project has no description', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(signedInRoutes({ body: { ...PROJECT, description: null } })),
    )
    await flushPromises()

    expect(wrapper.text()).toContain(messages.overview.noDescription)
  })

  it('links to the snapshot history without duplicating the list, and hides import for a viewer', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(signedInRoutes({ body: PROJECT })),
    )
    await flushPromises()

    expect(wrapper.get(`main a[href="/projects/${PROJECT_ID}/snapshots"]`).text()).toBe(
      messages.overview.other.browse,
    )
    expect(wrapper.find('.snapshot-list').exists()).toBe(false)
    expect(wrapper.find(`main a[href="/projects/${PROJECT_ID}/import"]`).exists()).toBe(false)
    expect(wrapper.find('.project-overview-import').exists()).toBe(false)
  })

  it('lets a project operator import a new snapshot right from the overview page', async () => {
    const dataMessages = catalogues[locale].data
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(
        signedInRoutes(
          { body: { ...PROJECT, current_user_role: 'operator' } },
          {
            [`/api/v1/projects/${PROJECT_ID}/snapshots`]: page([]),
            '/api/v1/snapshot-upload-limits': {
              body: {
                max_upload_part_bytes: 104857600,
                max_total_upload_bytes: 524288000,
                import_limits: { max_member_count: 128, max_total_expanded_bytes: 524288000 },
              },
            },
          },
        ),
      ),
    )
    await waitFor(() => expect(wrapper.find('.project-overview-import').exists()).toBe(true))
    const toggle = wrapper.get<HTMLButtonElement>('.project-overview-import')
    expect(toggle.text()).toBe(dataMessages.importAction)
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('#project-import-panel').isVisible()).toBe(false)

    await toggle.trigger('click')
    await waitFor(() => expect(wrapper.find('.import-file-input').exists()).toBe(true))
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(toggle.text()).toBe(dataMessages.hideImport)
    expect(wrapper.get('#project-import-panel').isVisible()).toBe(true)
  })

  it('shows a load error and retries when the project fails to load', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(
        signedInRoutes({
          body: { error: { code: 'resource_not_found', message: 'Gone.' } },
          init: { status: 404 },
        }),
      ),
    )
    await flushPromises()

    expect(wrapper.findAll('main h1')).toHaveLength(1)
    expect(wrapper.get('main h1').text()).toBe(catalogues[locale].nav.overview)
    expect(wrapper.get('main').text()).toContain(messages.overview.loadError)
    const feedback = wrapper.get('.project-overview-load-error')
    expect(feedback.classes()).toEqual(
      expect.arrayContaining(['app-feedback--critical', 'app-card']),
    )
  })

  it('redirects a signed-out visitor to the login page', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes({
        '/api/v1/branding': { body: {} },
        '/api/v1/me': {
          body: {
            error: { code: 'authentication_required', message: 'Authentication is required.' },
          },
          init: { status: 401 },
        },
      }),
    )

    // /login is lazy; its first import in this test file's process needs more than one
    // macrotask tick to resolve. See tests/helpers/wait.ts.
    await waitFor(() => {
      expect(wrapper.get('main h1').text()).toBe(catalogues[locale].login.title)
    })
  })
})

describe.each(['de', 'en'] as const)(
  'ProjectOverviewView statistics in %s',
  (locale: AppLocale) => {
    const messages = catalogues[locale].projects.overview

    async function mountOverview(
      project: unknown,
      more: Record<string, RouteResponse>,
    ): Promise<Awaited<ReturnType<typeof mountApplicationAt>>> {
      return mountApplicationAt(
        `/projects/${PROJECT_ID}/overview`,
        locale,
        apiClientWithRoutes(signedInRoutes({ body: project }, more)),
      )
    }

    /** The value and detail of the labelled figure whose label starts with `label`. */
    function stat(wrapper: Awaited<ReturnType<typeof mountApplicationAt>>, label: string): string {
      const found = wrapper
        .findAll('main .stat')
        .find((element) => element.get('.stat-label').text().startsWith(label))
      if (!found) throw new Error(`No figure labelled ${label}`)
      const detail = found.find('.stat-detail')
      return [found.get('.stat-value').text(), detail.exists() ? detail.text() : '']
        .filter(Boolean)
        .join(' ')
    }

    it('shows the team and the creation date in the details section', async () => {
      const wrapper = await mountOverview(PROJECT, {})
      await flushPromises()

      expect(wrapper.text()).toContain(messages.team)
      expect(wrapper.text()).toContain('Editorial Team')
      expect(wrapper.text()).toContain(messages.created)
    })

    it('puts the facts on one card and the dataset sections on plain sections, each with its own heading (D28)', async () => {
      const wrapper = await mountOverview(PROJECT, {})
      await waitFor(() => {
        const cards = wrapper.findAll('main .project-overview-card')
        expect(cards).toHaveLength(1)
        expect(cards[0]?.classes()).toEqual(
          expect.arrayContaining(['app-card', 'app-card--sectioned']),
        )
        // Matching Redigieren/Automatische Vorschläge (ProjectTaskView): the dataset sections are
        // plain, unboxed sections, not a second and third card.
        const sections = wrapper.findAll('main > section')
        expect(sections).toHaveLength(2)
        const headings = [cards[0], ...sections].map((el) => el?.find('h2').text())
        expect(headings).toEqual([messages.title, messages.data.title, messages.other.title])
      })
    })

    it('summarizes the latest ready snapshot and the runs on it', async () => {
      const wrapper = await mountOverview(PROJECT, {
        [`/api/v1/projects/${PROJECT_ID}/snapshots`]: page([
          snapshot('importing', { id: 'd0000000-0000-0000-0000-000000000009' }),
          snapshot('ready'),
          snapshot('failed', { id: 'd0000000-0000-0000-0000-000000000008' }),
        ]),
        [`/api/v1/snapshots/${SNAPSHOT_ID}/runs`]: page([{ id: RUN_ID }, { id: 'other' }]),
      })

      await waitFor(() => {
        expect(stat(wrapper, messages.data.snapshots)).toBe('3')
        expect(stat(wrapper, messages.data.records)).toBe('480')
        expect(stat(wrapper, messages.data.runs)).toBe('2')
        expect(stat(wrapper, messages.data.inProgress)).toBe('1')
        expect(stat(wrapper, messages.data.failed)).toBe('1')
      })
    })

    it('shows the newest snapshot as the present one, even while it is still importing', async () => {
      const wrapper = await mountOverview(PROJECT, {
        [`/api/v1/projects/${PROJECT_ID}/snapshots`]: page([
          snapshot('importing', { id: 'd0000000-0000-0000-0000-000000000009', ready_at: null }),
          snapshot('ready'),
        ]),
        [`/api/v1/snapshots/${SNAPSHOT_ID}/runs`]: page([{ id: RUN_ID }]),
      })

      await waitFor(() => {
        expect(wrapper.findAll('.snapshot')).toHaveLength(1)
      })
      const card = wrapper.get('.snapshot')
      expect(card.text()).toContain(catalogues[locale].projects.snapshots.status.importing)
      // The figures still summarize the last snapshot that finished, not the one shown above.
      expect(stat(wrapper, messages.data.runs)).toBe('1')
    })

    it('does not claim a total when the server has further snapshots', async () => {
      const wrapper = await mountOverview(PROJECT, {
        [`/api/v1/projects/${PROJECT_ID}/snapshots`]: {
          body: { items: [snapshot('ready')], has_more: true, next_cursor: 'next' },
        },
        [`/api/v1/snapshots/${SNAPSHOT_ID}/runs`]: page([]),
      })

      await waitFor(() => {
        expect(stat(wrapper, messages.data.snapshots)).toBe(fill(messages.atLeast, { count: 1 }))
      })
    })

    it('explains an empty project instead of showing zeros, and still links to the data', async () => {
      const wrapper = await mountOverview(PROJECT, {
        [`/api/v1/projects/${PROJECT_ID}/snapshots`]: page([]),
      })

      await waitFor(() => {
        expect(wrapper.text()).toContain(messages.data.empty)
      })
      expect(wrapper.find('main .stat').exists()).toBe(false)
      expect(wrapper.find(`main a[href="/projects/${PROJECT_ID}/snapshots"]`).exists()).toBe(true)
    })

    it('reports a snapshot load failure in its own section and keeps the data link', async () => {
      const wrapper = await mountOverview(PROJECT, {
        [`/api/v1/projects/${PROJECT_ID}/snapshots`]: NOT_FOUND,
      })

      await waitFor(() => {
        expect(wrapper.text()).toContain(messages.data.loadError)
      })
      expect(wrapper.get('main h1').text()).toBe('Project A')
    })
  },
)
