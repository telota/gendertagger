import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
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
  it('always links the brand to the start page', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))

    const brand = wrapper.get('aside a[href="/"]')
    expect(brand.text()).toBe(catalogues[locale].app.title)
  })

  it('offers one navigation item for the project list', async () => {
    const wrapper = await mountApplicationAt('/', locale, apiClientWithRoutes(NOT_SIGNED_IN))

    const projectsLink = wrapper.get('aside a[href="/projects"]')
    expect(projectsLink.text()).toBe(catalogues[locale].nav.projects)
  })

  it('marks the current location on the matching navigation item', async () => {
    const wrapper = await mountApplicationAt('/projects', locale, apiClientWithRoutes(SIGNED_IN))

    // /projects is lazy; its first import in this test file's process needs more than one
    // macrotask tick to resolve. See tests/helpers/wait.ts.
    await waitFor(() => {
      expect(wrapper.get('aside a[href="/projects"]').attributes('aria-current')).toBe('page')
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
}
const projectRoutes = (workingAggregation: string | null): Record<string, RouteResponse> => ({
  ...SIGNED_IN,
  [`/api/v1/projects/${PROJECT_ID}`]: {
    body: { ...PROJECT, working_aggregation_execution_id: workingAggregation },
  },
  [`/api/v1/aggregations/${AGGREGATION_ID}`]: {
    body: { id: AGGREGATION_ID, run_id: RUN_ID, status: 'completed' },
  },
  [`/api/v1/runs/${RUN_ID}`]: { body: { id: RUN_ID, dataset_snapshot_id: SNAPSHOT_ID } },
})

describe.each(['de', 'en'] as const)('AppSidebar project group in %s', (locale: AppLocale) => {
  const nav = catalogues[locale].nav
  const runBase = `/projects/${PROJECT_ID}/runs/${RUN_ID}`

  it('shows no project group outside a project', async () => {
    const wrapper = await mountApplicationAt('/projects', locale, apiClientWithRoutes(SIGNED_IN))
    await waitFor(() => expect(wrapper.find('aside a[href="/projects"]').exists()).toBe(true))

    expect(wrapper.get('aside').text()).not.toContain(nav.currentProject)
  })

  it('points the run entries at the working aggregation of the project', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(projectRoutes(AGGREGATION_ID)),
    )

    await waitFor(() => {
      expect(
        wrapper.find(`aside a[href="${runBase}/aggregations/${AGGREGATION_ID}/review"]`).text(),
      ).toBe(nav.review)
    })
    const aside = wrapper.get('aside')
    expect(aside.text()).toContain(nav.currentProject)
    expect(aside.get(`a[href="/projects/${PROJECT_ID}/import"]`).text()).toBe(nav.import)
    expect(aside.get(`a[href="${runBase}/aggregations/${AGGREGATION_ID}/people"]`).text()).toBe(
      nav.annotate,
    )
    expect(aside.get(`a[href="${runBase}/evaluations"]`).text()).toBe(nav.evaluations)
    expect(aside.get(`a[href="${runBase}/exports"]`).text()).toBe(nav.exports)
    await waitFor(() => {
      expect(
        wrapper
          .find(`aside a[href="/projects/${PROJECT_ID}/snapshots/${SNAPSHOT_ID}/runs"]`)
          .text(),
      ).toBe(nav.classification)
    })
  })

  it('disables the run entries, not links them, while the project has no working aggregation', async () => {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/overview`,
      locale,
      apiClientWithRoutes(projectRoutes(null)),
    )
    await waitFor(() => {
      expect(wrapper.findAll('aside [aria-disabled="true"]').length).toBe(5)
    })

    const disabled = wrapper.findAll('aside [aria-disabled="true"]').map((item) => item.text())
    expect(disabled).toEqual([
      nav.classification,
      nav.review,
      nav.annotate,
      nav.evaluations,
      nav.exports,
    ])
    expect(wrapper.find('aside a[href$="/review"]').exists()).toBe(false)
    expect(wrapper.get(`aside a[href="/projects/${PROJECT_ID}/overview"]`).text()).toBe(
      nav.overview,
    )
  })

  it('follows the run in the URL rather than the working aggregation', async () => {
    const otherRun = 'd0000000-0000-0000-0000-0000000000ff'
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/runs/${otherRun}/exports`,
      locale,
      apiClientWithRoutes(projectRoutes(null)),
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
