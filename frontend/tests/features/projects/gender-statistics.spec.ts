import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { mountApplicationAt } from '../../helpers/render'
import { apiClientWithRoutes, type RouteResponse } from '../../helpers/api'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const AGGREGATION_ID = 'e0000000-0000-0000-0000-000000000001'
const RUN_ID = 'f0000000-0000-0000-0000-000000000001'
const VIEWER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Viewer One', roles: [] }

function reviewGroup(
  certainty: string,
  label: string | null,
  count: number,
  workflow: string,
  action: string | null,
) {
  return {
    certainty_tier: certainty,
    agreement_tier: 'unanimous',
    final_label: label,
    result_count: count,
    review_action: action,
    workflow_state: workflow,
  }
}

/** 80 people: male 50, female 16 (10+6), unknown 4, institution 8, no final label 2. */
const REVIEW_SUMMARY = {
  aggregation_execution_id: AGGREGATION_ID,
  result_count: 80,
  last_annotated_at: null,
  groups: [
    reviewGroup('high', 'male', 50, 'unreviewed', null),
    reviewGroup('contested', 'female', 10, 'unreviewed', null),
    reviewGroup('contested', 'female', 6, 'reviewed', 'verify'),
    reviewGroup('low', 'unknown', 4, 'reviewed', 'correct'),
    reviewGroup('single', 'institution', 8, 'unreviewed', null),
    reviewGroup('uncertain', null, 2, 'deferred', 'defer'),
  ],
}

function project(workingAggregationId: string | null) {
  return {
    id: PROJECT_ID,
    slug: 'gender-project',
    display_name: 'Gender Project',
    current_user_role: 'viewer',
    current_user_can_manage_members: false,
    working_aggregation_execution_id: workingAggregationId,
    manager_user_id: VIEWER.id,
    created_by_user_id: VIEWER.id,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function signedInRoutes(
  workingAggregationId: string | null,
  more: Record<string, RouteResponse> = {},
): Record<string, RouteResponse> {
  return {
    '/api/v1/branding': { body: {} },
    '/api/v1/me': { body: VIEWER },
    '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    [`/api/v1/projects/${PROJECT_ID}`]: { body: project(workingAggregationId) },
    ...more,
  }
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('GenderStatisticsView in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].genderStatistics
  const path = `/projects/${PROJECT_ID}/gender-statistics`

  it('shows the gender ratio as a chart with an exact-count legend, once the aggregation completes', async () => {
    const wrapper = await mountApplicationAt(
      path,
      locale,
      apiClientWithRoutes(
        signedInRoutes(AGGREGATION_ID, {
          [`/api/v1/aggregations/${AGGREGATION_ID}`]: {
            body: { id: AGGREGATION_ID, run_id: RUN_ID, status: 'completed' },
          },
          [`/api/v1/aggregations/${AGGREGATION_ID}/review-summary`]: { body: REVIEW_SUMMARY },
        }),
      ),
    )
    await waitFor(() => expect(wrapper.find('.gender-statistics-chart').exists()).toBe(true))

    expect(wrapper.get('h1').text()).toBe(messages.title)
    const total = locale === 'de' ? '80 Personen insgesamt' : '80 people in total'
    expect(wrapper.text()).toContain(total)

    const entries = wrapper.findAll('.gender-statistics-entry')
    expect(entries).toHaveLength(5)
    const text = entries.map((entry) => entry.text())
    expect(text.some((line) => line.includes('male') && line.includes('50'))).toBe(true)
    expect(text.some((line) => line.includes('female') && line.includes('16'))).toBe(true)
    expect(text.some((line) => line.includes('unknown') && line.includes('4'))).toBe(true)
    expect(text.some((line) => line.includes('institution') && line.includes('8'))).toBe(true)
    expect(
      text.some(
        (line) =>
          line.includes(catalogues[locale].projects.overview.review.noLabel) &&
          line.includes('2'),
      ),
    ).toBe(true)
    expect(wrapper.findAll('circle')).toHaveLength(5)
  })

  it('links back to Gender taggen above the heading', async () => {
    const wrapper = await mountApplicationAt(
      path,
      locale,
      apiClientWithRoutes(signedInRoutes(null)),
    )
    await flushPromises()
    const link = wrapper.get(`main a[href="/projects/${PROJECT_ID}/gender-tagging"]`)
    expect(link.text()).toBe(catalogues[locale].genderTagging.review.goToOverview)
  })

  it('explains there is nothing to show yet when the project has no working aggregation', async () => {
    const wrapper = await mountApplicationAt(
      path,
      locale,
      apiClientWithRoutes(signedInRoutes(null)),
    )
    await flushPromises()
    expect(wrapper.text()).toContain(messages.noWorkingAggregation)
    expect(wrapper.find('.gender-statistics-chart').exists()).toBe(false)
  })

  it('names the status instead of a chart while the aggregation has not completed', async () => {
    const wrapper = await mountApplicationAt(
      path,
      locale,
      apiClientWithRoutes(
        signedInRoutes(AGGREGATION_ID, {
          [`/api/v1/aggregations/${AGGREGATION_ID}`]: {
            body: { id: AGGREGATION_ID, run_id: RUN_ID, status: 'failed' },
          },
        }),
      ),
    )
    await waitFor(() =>
      expect(wrapper.text()).toContain(
        messages.notCompleted.replace('{status}', 'failed'),
      ),
    )
    expect(wrapper.find('.gender-statistics-chart').exists()).toBe(false)
  })
})
