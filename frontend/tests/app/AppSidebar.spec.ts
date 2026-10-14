import { afterEach, describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import type { AppLocale } from '@/app/i18n'
import { createAppRouter } from '@/app/router'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const

const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer One', roles: [] }
const NOT_SIGNED_IN: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': {
    body: { error: { code: 'authentication_required', message: 'Authentication is required.' } },
    init: { status: 401 },
  },
}
const SIGNED_IN: Record<string, RouteResponse> = {
  '/api/v1/branding': { body: {} },
  '/api/v1/me': { body: USER },
  '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
  '/api/v1/projects': { body: { items: [], has_more: false, next_cursor: null } },
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('AppSidebar in %s', (locale: AppLocale) => {
  it('moves the home brand to the header when signed out', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))

    expect(wrapper.find('aside').exists()).toBe(false)
    const brand = wrapper.get('.app-header-brand')
    expect(brand.attributes('href')).toBe('/')
    expect(brand.text()).toBe(catalogues[locale].app.title)
  })

  it('offers the Projekte tab to a signed-in user even without accessible projects', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(SIGNED_IN))

    await waitFor(() => {
      expect(wrapper.get('aside nav a[href="/"]').text()).toBe(catalogues[locale].nav.projects)
    })
  })

  it('marks the current location on the matching navigation item', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(SIGNED_IN))

    // / is lazy; its first import in this test file's process needs more than one macrotask tick
    // to resolve. See tests/helpers/wait.ts.
    await waitFor(() => {
      expect(wrapper.get('aside nav a[href="/"]').attributes('aria-current')).toBe('page')
    })
  })
})

const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
const RUN_ID = 'd0000000-0000-0000-0000-000000000001'
const AGGREGATION_ID = 'e0000000-0000-0000-0000-000000000001'
const PROJECT = {
  id: PROJECT_ID,
  slug: 'project-a',
  display_name: 'Project A',
  current_user_role: 'operator',
  created_at: '2026-01-01T00:00:00Z',
  team: {
    id: 'c0000000-0000-0000-0000-0000000000f1',
    slug: 'editors',
    display_name: 'Editorial Team',
    created_at: '2026-01-01T00:00:00Z',
  },
}
const projectRoutes = (workingAggregation: string | null): Record<string, RouteResponse> => ({
  ...SIGNED_IN,
  [`/api/v1/projects/${PROJECT_ID}`]: {
    body: { ...PROJECT, working_aggregation_execution_id: workingAggregation },
  },
  [`/api/v1/projects/${PROJECT_ID}/data-availability`]: {
    body: { project_id: PROJECT_ID, has_ready_snapshots: true, has_completed_aggregations: true },
  },
  [`/api/v1/aggregations/${AGGREGATION_ID}`]: {
    body: { id: AGGREGATION_ID, run_id: RUN_ID, status: 'completed' },
  },
  [`/api/v1/runs/${RUN_ID}`]: { body: { id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID } },
  [`/api/v1/snapshots/${SNAPSHOT_ID}`]: {
    body: { id: SNAPSHOT_ID, project_id: PROJECT_ID, status: 'ready' },
  },
})

describe.each(['de', 'en'] as const)('AppSidebar project group in %s', (locale: AppLocale) => {
  const nav = catalogues[locale].nav
  const runBase = `/projects/${PROJECT_ID}/runs/${RUN_ID}`

  it('shows no project group outside a project', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(SIGNED_IN))
    await waitFor(() => expect(wrapper.find('aside nav a[href="/"]').exists()).toBe(true))

    expect(wrapper.find('aside .project-switcher').exists()).toBe(false)
  })

  it('hides the project switcher in guided mode: there is no Übersicht to switch into', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/gender-tagging`,
      locale,
      apiClientWithRoutes({
        ...projectRoutes(null),
        '/api/v1/me/preferences': {
          body: {
            locale: null,
            theme: 'system',
            desktop_sidebar_collapsed: false,
            interface_mode: 'guided',
            revision: 1,
          },
        },
      }),
    )
    await waitFor(() =>
      expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/gender-tagging"]`).exists()).toBe(
        true,
      ),
    )
    expect(wrapper.find('aside .project-switcher').exists()).toBe(false)
  })

  it.each([AGGREGATION_ID, null])(
    'opens the one Redigieren task picker regardless of working pointer %s',
    async (working) => {
      const wrapper = await mountApplicationAt(
        `/projects/${PROJECT_ID}/overview`,
        locale,
        apiClientWithRoutes(projectRoutes(working)),
      )
      await waitFor(() =>
        expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/annotation"]`).exists()).toBe(
          true,
        ),
      )
      expect(wrapper.get(`aside a[href="/projects/${PROJECT_ID}/classification"]`).text()).toBe(
        nav.classification,
      )
      expect(wrapper.get(`aside a[href="/projects/${PROJECT_ID}/annotation"]`).text()).toBe(
        nav.review,
      )
      expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/review"]`).exists()).toBe(false)
      expect(wrapper.find('aside a[href$="/evaluations"]').exists()).toBe(false)
      expect(wrapper.find('aside a[href$="/exports"]').exists()).toBe(false)
      expect(wrapper.findAll('aside [aria-disabled="true"]')).toHaveLength(0)
    },
  )

  it('hides actual unavailable tasks in an empty project', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes({
        ...projectRoutes(null),
        [`/api/v1/projects/${PROJECT_ID}/data-availability`]: {
          body: {
            project_id: PROJECT_ID,
            has_ready_snapshots: false,
            has_completed_aggregations: false,
          },
        },
      }),
    )
    await waitFor(() =>
      expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/overview"]`).exists()).toBe(true),
    )
    expect(wrapper.findAll('aside nav .nav-item').map((item) => item.text())).toEqual([
      nav.overview,
    ])
    expect(wrapper.findAll('aside [aria-disabled="true"]')).toHaveLength(0)
    expect(
      wrapper
        .findAll('aside .app-sidebar-section')
        .every((group) => group.findAll('li').length > 0),
    ).toBe(true)
  })

  it('clears explicit run destinations when returning to overview', async () => {
    const router = createAppRouter(createMemoryHistory())
    const wrapper = await mountApplicationAt(
      `${runBase}/exports`,
      locale,
      apiClientWithRoutes(projectRoutes(AGGREGATION_ID)),
      router,
    )
    await waitFor(() =>
      expect(wrapper.find(`aside a[href="${runBase}/evaluations"]`).exists()).toBe(true),
    )
    await router.push(`/projects/${PROJECT_ID}/overview`)
    await waitFor(() => expect(wrapper.find('aside a[href$="/exports"]').exists()).toBe(false))
    expect(wrapper.find('aside a[href$="/evaluations"]').exists()).toBe(false)
    expect(wrapper.find(`aside a[href="/projects/${PROJECT_ID}/annotation"]`).exists()).toBe(true)
  })

  it('follows the run in the URL rather than the working aggregation', async () => {
    const otherRun = 'd0000000-0000-0000-0000-0000000000ff'
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/runs/${otherRun}/exports`,
      locale,
      apiClientWithRoutes({
        ...projectRoutes(null),
        [`/api/v1/runs/${otherRun}`]: {
          body: { id: otherRun, dataset_snapshot_id: SNAPSHOT_ID },
        },
      }),
    )

    await waitFor(() => {
      expect(
        wrapper
          .find(`aside a[href="/projects/${PROJECT_ID}/runs/${otherRun}/evaluations"]`)
          .exists(),
      ).toBe(true)
    })
  })
})
