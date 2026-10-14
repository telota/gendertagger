import { useQueryClient } from '@tanstack/vue-query'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createApiClient, type components } from '@/api'
import { useSessionStore } from '@/stores/session'

import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

const USER = { id: 'user-a', display_name: 'Source reader', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
const OTHER_SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000002'
const PATH = `/projects/${PROJECT_ID}/snapshots/${SNAPSHOT_ID}`
const API_PATH = `/api/v1/snapshots/${SNAPSHOT_ID}`
const STATISTICS_API_PATH = `${API_PATH}/statistics`
const HASH = 'ab'.repeat(32)

function snapshot(
  overrides: Partial<components['schemas']['DatasetSnapshot']> = {},
): components['schemas']['DatasetSnapshot'] {
  return {
    id: SNAPSHOT_ID,
    project_id: PROJECT_ID,
    source_artifact_id: 'source-artifact',
    source_sha256: HASH,
    parser_version: 'tei-parser-7',
    import_config: { source_format: 'tei' },
    status: 'ready',
    record_count: 2,
    created_at: '2026-03-04T10:15:00Z',
    ready_at: '2026-03-04T10:16:00Z',
    ...overrides,
  }
}

function statistics(
  overrides: Partial<components['schemas']['DatasetSnapshotStatistics']> = {},
): components['schemas']['DatasetSnapshotStatistics'] {
  return {
    dataset_snapshot_id: SNAPSHOT_ID,
    total_person_count: 2,
    source_gender: {
      with_element_count: 1,
      without_element_count: 1,
      male_count: 0,
      female_count: 1,
      unknown_count: 0,
      institution_count: 0,
      other_or_multiple_count: 0,
    },
    gnd: {
      with_reference_count: 1,
      without_reference_count: 1,
      with_reference_and_source_gender_count: 1,
    },
    ...overrides,
  }
}

function person(
  teiId = 'person.exact_42',
  snapshotId = SNAPSHOT_ID,
): components['schemas']['PersonRecord'] {
  return {
    id: `persisted-${teiId}`,
    dataset_snapshot_id: snapshotId,
    tei_id: teiId,
    forenames: ['Ada'],
    surname: teiId === 'person.exact_42' ? 'Lovelace' : 'Byron',
    note: `Source note for ${teiId}`,
    gnd_id: teiId === 'person.exact_42' ? '118540238' : null,
    source_member_name: 'register.xml',
    source_record_locator: `/TEI/listPerson/person[@xml:id='${teiId}']`,
    created_at: '2026-03-04T10:16:00Z',
  }
}

function json(body: unknown, status = 200): Response {
  return Response.json(body, { status })
}

function failure(status = 500): Response {
  return json({ error: { code: 'resource_not_found', message: 'Unavailable.' } }, status)
}

function page(items: unknown[], cursor: string | null = null): Response {
  return json({ items, has_more: cursor !== null, next_cursor: cursor })
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

type Handler = (request: Request) => Response | Promise<Response> | undefined

function server(extra: Handler = () => undefined) {
  const requests: Request[] = []
  const client = createApiClient({
    fetch: async (request) => {
      requests.push(request)
      const handled = await extra(request)
      if (handled) return handled
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/branding') return json({})
      if (pathname === '/api/v1/me') return json(USER)
      if (pathname === '/api/v1/auth/session')
        return json({ must_change_password: false, keep_signed_in: false })
      if (pathname === '/api/v1/me/preferences')
        return json({
          locale: null,
          theme: 'system',
          desktop_sidebar_collapsed: false,
          revision: 1,
        })
      if (pathname === '/api/v1/projects') return page([])
      if (pathname === `/api/v1/projects/${PROJECT_ID}`)
        return json({
          id: PROJECT_ID,
          slug: 'edition',
          display_name: 'Source edition',
          current_user_role: 'viewer',
          current_user_can_manage_members: false,
          working_aggregation_execution_id: null,
          manager_user_id: 'manager',
          created_by_user_id: 'manager',
          created_at: '2026-01-01T00:00:00Z',
        })
      if (pathname === API_PATH) return json(snapshot())
      if (pathname === STATISTICS_API_PATH) return json(statistics())
      if (pathname === `${API_PATH}/source-members`)
        return json([
          {
            id: 'member-a',
            dataset_snapshot_id: SNAPSHOT_ID,
            artifact_id: 'artifact-a',
            logical_name: 'register.xml',
            media_type: 'application/tei+xml',
            byte_size: 2048,
            ordinal: 0,
            sha256: 'cd'.repeat(32),
            created_at: '2026-03-04T10:15:00Z',
          },
        ])
      if (pathname === `${API_PATH}/people`) return page([person()])
      if (pathname === `${API_PATH}/people/person.exact_42`) return json(person())
      return failure(404)
    },
  })
  return {
    client,
    requests,
    paths: () => requests.map((request) => new URL(request.url).pathname),
  }
}

enableAutoUnmount(afterEach)
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('snapshot detail in %s', (locale) => {
  it('exposes provenance and the exact TEI source record without classification requests', async () => {
    const state = server()
    const wrapper = await mountApplicationAt(PATH, locale, state.client)
    await waitFor(() => expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(1))
    expect(wrapper.findAll('main h1')).toHaveLength(1)
    expect(wrapper.get('main').text()).toContain('tei-parser-7')
    expect(wrapper.get('main').text()).toContain(HASH)
    expect(wrapper.get('main').text()).toContain('register.xml')
    expect(wrapper.findAll('.snapshot-record-table thead th')).toHaveLength(4)
    const inventory = wrapper.get('.snapshot-statistics')
    expect(inventory.text()).toContain(locale === 'de' ? 'Bestandsübersicht' : 'Dataset inventory')
    expect(inventory.findAll('progress')).toHaveLength(8)
    const distribution = inventory.findAll('.snapshot-statistics-distribution .snapshot-statistic')
    expect(distribution).toHaveLength(5)
    for (const [index, category] of [
      'male',
      'female',
      'unknown',
      'institution',
      'other',
    ].entries()) {
      expect(distribution[index]?.classes()).toContain(`snapshot-statistic--${category}`)
      expect(distribution[index]?.get('progress').attributes('aria-label')).toBeTruthy()
    }
    expect(distribution[4]?.classes()).not.toContain('snapshot-statistic--unknown')
    expect(inventory.text()).toContain(locale === 'de' ? '1 von 2' : '1 of 2')
    expect(wrapper.get('.snapshot-record-gnd-badge').attributes('aria-label')).toContain(
      '118540238',
    )

    const action = wrapper.get<HTMLElement>('.snapshot-record-view')
    expect(action.attributes('aria-expanded')).toBe('false')
    expect(action.attributes('aria-controls')).toBeUndefined()
    const metadataCards = wrapper.get('.snapshot-secondary')
    const sources = wrapper.get('details.snapshot-sources')
    const provenance = wrapper.get('details.snapshot-provenance')
    const summary = wrapper.get('.snapshot-summary')
    expect(summary.classes()).toEqual(expect.arrayContaining(['app-card', 'app-fact-list']))
    expect(summary.findAll('.app-fact-list__item')).toHaveLength(2)
    expect(provenance.classes()).toEqual(
      expect.arrayContaining(['app-card', 'app-card--sectioned']),
    )
    expect(provenance.findAll('.app-fact-list__item')).toHaveLength(3)
    expect(provenance.find('.app-card').exists()).toBe(false)
    expect(sources.attributes('open')).toBeUndefined()
    expect(provenance.attributes('open')).toBeUndefined()
    expect(
      metadataCards.element.compareDocumentPosition(wrapper.get('.snapshot-records').element) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    await action.trigger('click')
    await waitFor(() =>
      expect(wrapper.get('.snapshot-record-detail').text()).toContain(
        'Source note for person.exact_42',
      ),
    )
    expect(wrapper.get('.snapshot-record-view').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.snapshot-record-view').attributes('aria-controls')).toBe(
      'snapshot-record-detail-panel',
    )
    expect(wrapper.get('.snapshot-record-view').text()).toBe(
      locale === 'de' ? 'Schließen' : 'Close',
    )
    expect(wrapper.find('.snapshot-record-close').exists()).toBe(false)
    const summaryRow = wrapper.get('.snapshot-record-row--selected')
    const detailRow = wrapper.get('.snapshot-record-detail-row')
    expect(summaryRow.element.nextElementSibling).toBe(detailRow.element)
    expect(detailRow.get('td').attributes('colspan')).toBe('4')
    expect(document.activeElement).toBe(wrapper.get('#snapshot-record-detail-panel').element)
    expect(wrapper.find('.snapshot-record-detail-heading').exists()).toBe(false)
    expect(wrapper.get('.snapshot-record-detail').classes()).not.toContain('app-resource-card')
    expect(wrapper.get('.snapshot-record-detail').classes()).toContain(
      'snapshot-record-detail--embedded',
    )
    expect(
      wrapper
        .get('.snapshot-record-table-scroll')
        .find('.app-card .app-card, .app-card .app-resource-card')
        .exists(),
    ).toBe(false)
    expect(wrapper.vm.$router.currentRoute.value.query.person).toBe('person.exact_42')
    expect(state.paths()).toContain(`${API_PATH}/people/person.exact_42`)
    expect(state.paths().some((path) => /predictions|annotations|review-items/.test(path))).toBe(
      false,
    )
    expect(state.requests.every((request) => request.method === 'GET')).toBe(true)
    await sources.get('summary').trigger('click')
    await provenance.get('summary').trigger('click')
    await expectNoAxeViolations(wrapper.get('main').element)
    await wrapper.get('.snapshot-record-row--selected .snapshot-record-view').trigger('click')
    await waitFor(() => expect(wrapper.vm.$router.currentRoute.value.query.person).toBeUndefined())
    expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(1)
    expect(wrapper.find('.snapshot-record-detail-row').exists()).toBe(false)
    expect(wrapper.get('.snapshot-record-view').attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(wrapper.get('.snapshot-record-view').element)
  })

  it('distinguishes uncaptured source gender from a zero count', async () => {
    const state = server((request) => {
      if (new URL(request.url).pathname !== STATISTICS_API_PATH) return undefined
      return json(
        statistics({
          source_gender: null,
          gnd: {
            with_reference_count: 1,
            without_reference_count: 1,
            with_reference_and_source_gender_count: null,
          },
        }),
      )
    })

    const wrapper = await mountApplicationAt(PATH, locale, state.client)
    await waitFor(() => expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(1))
    const inventory = wrapper.get('.snapshot-statistics')
    expect(inventory.findAll('progress')).toHaveLength(1)
    expect(inventory.text()).toContain(locale === 'de' ? 'Nicht erfasst' : 'Not captured')
    expect(inventory.text()).toContain(
      locale === 'de' ? 'nicht statistisch erfasst' : 'were not captured statistically',
    )
  })

  it('retains one page heading while a snapshot loads and fails', async () => {
    const response = deferredResponse()
    const state = server((request) =>
      new URL(request.url).pathname === API_PATH ? response.promise : undefined,
    )
    const wrapper = await mountApplicationAt(PATH, locale, state.client)
    await waitFor(() => expect(wrapper.findAll('main h1')).toHaveLength(1))
    expect(wrapper.get('main h1').text()).not.toBe('')
    expect(wrapper.get('.snapshot-detail > .app-feedback').classes()).toContain('app-card')
    response.resolve(failure())
    await waitFor(() => expect(wrapper.find('main [role="alert"]').exists()).toBe(true))
    expect(wrapper.get('.snapshot-detail > .app-feedback').classes()).toContain('app-card')
    expect(wrapper.findAll('main h1')).toHaveLength(1)
    expect(state.paths().some((path) => path.startsWith(`${API_PATH}/`))).toBe(false)
  })

  it('keeps loaded records through pagination failure, retry, selection, and return', async () => {
    const cursors: (string | null)[] = []
    const state = server((request) => {
      const url = new URL(request.url)
      if (url.pathname !== `${API_PATH}/people`) return undefined
      cursors.push(url.searchParams.get('cursor'))
      if (cursors.length === 1) return page([person()], 'next-page')
      if (cursors.length === 2) return failure()
      return page([person('person.second')])
    })
    const wrapper = await mountApplicationAt(PATH, locale, state.client)
    await waitFor(() => expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(1))
    await wrapper.get('.snapshot-records-more').trigger('click')
    await waitFor(() =>
      expect(wrapper.find('.snapshot-records [role="alert"]').exists()).toBe(true),
    )
    expect(wrapper.get('.snapshot-record-feedback').classes()).not.toContain('app-card')
    expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(1)
    await wrapper.get('.snapshot-records-retry').trigger('click')
    await waitFor(() => expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(2))
    expect(wrapper.get('.snapshot-record-gnd-missing').attributes('aria-label')).toBe(
      locale === 'de' ? 'Keine GND-Referenz' : 'No GND reference',
    )
    expect(cursors).toEqual([null, 'next-page', 'next-page'])
    await wrapper.findAll('.snapshot-record-view')[0]!.trigger('click')
    await waitFor(() => expect(wrapper.find('.snapshot-record-detail .record').exists()).toBe(true))
    await wrapper.get('.snapshot-record-row--selected .snapshot-record-view').trigger('click')
    await waitFor(() => expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(2))
    expect(cursors).toEqual([null, 'next-page', 'next-page'])
  })
})

const AGGREGATION_ID = 'e0000000-0000-0000-0000-000000000001'
const RUN_ID = 'f0000000-0000-0000-0000-000000000001'

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

/** 80 people: 10 reviewed (6 confirmed, 4 corrected), 2 deferred, 68 not yet reviewed. */
const REVIEW_SUMMARY = {
  aggregation_execution_id: AGGREGATION_ID,
  result_count: 80,
  last_annotated_at: '2026-02-03T09:00:00Z',
  groups: [
    reviewGroup('high', 'male', 50, 'unreviewed', null),
    reviewGroup('contested', 'female', 10, 'unreviewed', null),
    reviewGroup('contested', 'female', 6, 'reviewed', 'verify'),
    reviewGroup('low', 'unknown', 4, 'reviewed', 'correct'),
    reviewGroup('single', 'institution', 8, 'unreviewed', null),
    reviewGroup('uncertain', null, 2, 'deferred', 'defer'),
  ],
}

const AGGREGATION = {
  id: AGGREGATION_ID,
  run_id: RUN_ID,
  status: 'completed',
  strategy: 'reference_v1',
  method_execution_ids: [],
  config_sha256: 'abc',
  created_at: '2026-02-02T10:00:00Z',
}

/** `server()` plus the project/aggregation/run routes D28's "Stand der Prüfung" gating needs. */
function serverWithWorkingAggregation(
  workingAggregationId: string | null,
  runDatasetSnapshotId: string,
  extra: Handler = () => undefined,
) {
  return server((request) => {
    const overridden = extra(request)
    if (overridden) return overridden
    const path = new URL(request.url).pathname
    if (path === `/api/v1/projects/${PROJECT_ID}`) {
      return json({
        id: PROJECT_ID,
        slug: 'edition',
        display_name: 'Source edition',
        current_user_role: 'viewer',
        current_user_can_manage_members: false,
        working_aggregation_execution_id: workingAggregationId,
        manager_user_id: 'manager',
        created_by_user_id: 'manager',
        created_at: '2026-01-01T00:00:00Z',
      })
    }
    if (path === `/api/v1/aggregations/${AGGREGATION_ID}`) return json(AGGREGATION)
    if (path === `/api/v1/runs/${RUN_ID}`)
      return json({ id: RUN_ID, dataset_snapshot_id: runDatasetSnapshotId })
    if (path === `/api/v1/aggregations/${AGGREGATION_ID}/review-summary`) return json(REVIEW_SUMMARY)
    return undefined
  })
}

describe.each(['de', 'en'] as const)('snapshot detail review stats (D28) in %s', (locale) => {
  it('shows review progress when this dataset backs the working aggregation', async () => {
    const state = serverWithWorkingAggregation(AGGREGATION_ID, SNAPSHOT_ID)
    const wrapper = await mountApplicationAt(PATH, locale, state.client)
    await waitFor(() => {
      expect(wrapper.text()).toContain(
        locale === 'de' ? 'Stand der Prüfung' : 'Review progress',
      )
      expect(wrapper.text()).toContain(
        locale === 'de' ? '10 von 80 Personen geprüft' : '10 of 80 people reviewed',
      )
    })
    expect(wrapper.get('.snapshot-review-stats progress').attributes('value')).toBe('12.5')
  })

  it('shows a not-current note with a link to the current dataset otherwise', async () => {
    const state = serverWithWorkingAggregation(AGGREGATION_ID, OTHER_SNAPSHOT_ID)
    const wrapper = await mountApplicationAt(PATH, locale, state.client)
    await waitFor(() => {
      expect(wrapper.text()).toContain(
        locale === 'de'
          ? 'Dies ist nicht der Datenstand, der die aktuelle Arbeitsaggregation des Projekts trägt'
          : "This is not the dataset behind the project's current working aggregation",
      )
    })
    expect(
      wrapper.find(`main a[href="/projects/${PROJECT_ID}/snapshots/${OTHER_SNAPSHOT_ID}"]`).text(),
    ).toBe(locale === 'de' ? 'Zum aktuellen Datenstand' : 'Go to the current dataset')
    expect(wrapper.text()).not.toContain(
      locale === 'de' ? '10 von 80 Personen geprüft' : '10 of 80 people reviewed',
    )
  })

  it('shows nothing when the project has no working aggregation at all', async () => {
    const state = serverWithWorkingAggregation(null, SNAPSHOT_ID)
    const wrapper = await mountApplicationAt(PATH, locale, state.client)
    await waitFor(() => expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(1))
    expect(wrapper.find('.snapshot-review-stats').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(locale === 'de' ? 'Stand der Prüfung' : 'Review progress')
  })

  it('offers a retry when the working aggregation fails to load', async () => {
    let failing = true
    const state = serverWithWorkingAggregation(AGGREGATION_ID, SNAPSHOT_ID, (request) =>
      new URL(request.url).pathname === `/api/v1/aggregations/${AGGREGATION_ID}` && failing
        ? failure()
        : undefined,
    )
    const wrapper = await mountApplicationAt(PATH, locale, state.client)
    await waitFor(() => expect(wrapper.find('.snapshot-review-stats button').exists()).toBe(true))
    failing = false
    await wrapper.get('.snapshot-review-stats button').trigger('click')
    await waitFor(() =>
      expect(wrapper.text()).toContain(
        locale === 'de' ? '10 von 80 Personen geprüft' : '10 of 80 people reviewed',
      ),
    )
  })
})

it('cards the records loading and empty replacement states', async () => {
  const response = deferredResponse()
  const state = server((request) =>
    new URL(request.url).pathname === `${API_PATH}/people` ? response.promise : undefined,
  )
  const wrapper = await mountApplicationAt(PATH, 'en', state.client)

  await waitFor(() => expect(wrapper.find('.snapshot-record-list-status').exists()).toBe(true))
  expect(wrapper.get('.snapshot-record-list-status').classes()).toContain('app-card')

  response.resolve(page([]))
  await waitFor(() => expect(wrapper.find('.snapshot-records-empty').exists()).toBe(true))
  expect(wrapper.get('.snapshot-records-empty').classes()).toContain('app-card')
})

it('cards an initial records failure and its recovery', async () => {
  let failing = true
  const state = server((request) => {
    if (new URL(request.url).pathname !== `${API_PATH}/people`) return undefined
    return failing ? failure() : page([])
  })
  const wrapper = await mountApplicationAt(PATH, 'en', state.client)

  await waitFor(() => expect(wrapper.find('.snapshot-record-feedback').exists()).toBe(true))
  expect(wrapper.get('.snapshot-record-feedback').classes()).toContain('app-card')

  failing = false
  await wrapper.get('.snapshot-records-retry').trigger('click')
  await waitFor(() => expect(wrapper.find('.snapshot-records-empty').exists()).toBe(true))
  expect(wrapper.get('.snapshot-records-empty').classes()).toContain('app-card')
})

it('keeps the person list usable when snapshot statistics fail', async () => {
  const state = server((request) =>
    new URL(request.url).pathname === STATISTICS_API_PATH ? failure() : undefined,
  )

  const wrapper = await mountApplicationAt(PATH, 'en', state.client)
  await waitFor(() => expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(1))
  await waitFor(() =>
    expect(wrapper.find('.snapshot-statistics [role="status"]').exists()).toBe(true),
  )
  expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(1)
  expect(wrapper.find('.snapshot-statistics button').exists()).toBe(true)
})

it.each(['pending', 'importing'] as const)(
  'polls a %s import and waits for readiness before requesting raw people',
  async (status) => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    let snapshotReads = 0
    const state = server((request) => {
      if (new URL(request.url).pathname !== API_PATH) return undefined
      snapshotReads += 1
      return json(snapshot({ status: snapshotReads === 1 ? status : 'ready' }))
    })
    const wrapper = await mountApplicationAt(PATH, 'en', state.client)
    await waitFor(() => expect(snapshotReads).toBe(1))
    expect(wrapper.findAll('main h1')).toHaveLength(1)
    expect(state.paths()).not.toContain(`${API_PATH}/people`)
    await vi.advanceTimersByTimeAsync(2100)
    await waitFor(() => expect(wrapper.findAll('.snapshot-record-view')).toHaveLength(1))
    const readyReads = snapshotReads
    await vi.advanceTimersByTimeAsync(6000)
    expect(snapshotReads).toBe(readyReads)
  },
)

it('revalidates an active import immediately on invalidation and clears denied snapshot data', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  let denied = false
  let snapshotReads = 0
  const state = server((request) => {
    if (new URL(request.url).pathname !== API_PATH) return undefined
    snapshotReads += 1
    return denied ? failure(403) : json(snapshot({ status: 'importing' }))
  })
  const wrapper = await mountApplicationAt(PATH, 'en', state.client)
  await waitFor(() =>
    expect(wrapper.find('.snapshot-summary-status--importing').exists()).toBe(true),
  )
  expect(snapshotReads).toBe(1)

  denied = true
  const queryClient = wrapper.vm.$.appContext.app.runWithContext(() => useQueryClient())
  await queryClient.invalidateQueries({
    queryKey: ['imported-snapshot', USER.id, PROJECT_ID, SNAPSHOT_ID],
    exact: true,
  })
  await waitFor(() => expect(wrapper.find('main [role="alert"]').exists()).toBe(true))
  expect(snapshotReads).toBe(2)
  expect(wrapper.find('.snapshot-summary').exists()).toBe(false)
  expect(wrapper.find(`main a[href="${PATH}/runs"]`).exists()).toBe(false)
  await vi.advanceTimersByTimeAsync(2100)
  expect(snapshotReads).toBe(2)
})

it('shows an exact deep-linked record separately when it is outside the loaded cursor page', async () => {
  const state = server((request) => {
    const { pathname, searchParams } = new URL(request.url)
    if (pathname === `${API_PATH}/people`) {
      if (searchParams.get('cursor') === 'next-page') return page([person()])
      return page([person('person.on-page')], 'next-page')
    }
    if (pathname === `${API_PATH}/people/person.exact_42`) return json(person())
    return undefined
  })

  const wrapper = await mountApplicationAt(`${PATH}?person=person.exact_42`, 'en', state.client)
  await waitFor(() => {
    expect(wrapper.findAll('.snapshot-record-row')).toHaveLength(1)
    expect(wrapper.get('.snapshot-record-standalone .record').text()).toContain(
      'Source note for person.exact_42',
    )
  })

  expect(wrapper.get('.snapshot-record-context').text()).not.toBe('')
  expect(wrapper.get('.snapshot-record-table').text()).toContain('person.on-page')
  expect(wrapper.get('.snapshot-record-table').text()).not.toContain('person.exact_42')
  expect(wrapper.find('.snapshot-record-detail-row').exists()).toBe(false)
  expect(
    wrapper.get('.snapshot-record-row .snapshot-record-view').attributes('aria-expanded'),
  ).toBe('false')
  expect(wrapper.get('.snapshot-record-external-toggle').attributes('aria-expanded')).toBe('true')
  expect(wrapper.vm.$router.currentRoute.value.query.person).toBe('person.exact_42')
  expect(state.paths()).toContain(`${API_PATH}/people/person.exact_42`)

  const standalone = wrapper.get('.snapshot-record-standalone').element
  await wrapper.get('.snapshot-records-more').trigger('click')
  await waitFor(() => expect(wrapper.findAll('.snapshot-record-row')).toHaveLength(2))
  expect(wrapper.get('.snapshot-record-standalone').element).toBe(standalone)
  expect(wrapper.find('.snapshot-record-detail-row').exists()).toBe(false)
})

it('waits for the first records page before placing an exact deep-linked record', async () => {
  const list = deferredResponse()
  const state = server((request) =>
    new URL(request.url).pathname === `${API_PATH}/people` ? list.promise : undefined,
  )
  const wrapper = await mountApplicationAt(`${PATH}?person=person.exact_42`, 'en', state.client)
  await waitFor(() => expect(state.paths()).toContain(`${API_PATH}/people/person.exact_42`))
  expect(wrapper.find('.snapshot-record-detail').exists()).toBe(false)

  list.resolve(page([person()]))
  await waitFor(() => expect(wrapper.find('.snapshot-record-detail-row').exists()).toBe(true))
  expect(wrapper.find('.snapshot-record-standalone').exists()).toBe(false)
  expect(wrapper.findAll('#snapshot-record-detail-panel')).toHaveLength(1)
})

it.each([{ id: OTHER_SNAPSHOT_ID }, { project_id: 'another-project' }])(
  'rejects a snapshot outside the route identity: %j',
  async (overrides) => {
    const state = server((request) =>
      new URL(request.url).pathname === API_PATH ? json(snapshot(overrides)) : undefined,
    )
    const wrapper = await mountApplicationAt(PATH, 'en', state.client)
    await waitFor(() => expect(wrapper.find('main [role="alert"]').exists()).toBe(true))
    expect(wrapper.findAll('main h1')).toHaveLength(1)
    expect(state.paths().some((path) => path.startsWith(`${API_PATH}/`))).toBe(false)
    expect(wrapper.find('main a[href$="/runs"]').exists()).toBe(false)
    expect(wrapper.find('.snapshot-records').exists()).toBe(false)
  },
)

it.each([{ dataset_snapshot_id: OTHER_SNAPSHOT_ID }, { tei_id: 'different-person' }])(
  'rejects a selected record with a mismatched identity: %j',
  async (overrides) => {
    const state = server((request) =>
      new URL(request.url).pathname === `${API_PATH}/people/person.exact_42`
        ? json({ ...person(), ...overrides, note: 'Wrong identity must stay hidden' })
        : undefined,
    )
    const wrapper = await mountApplicationAt(`${PATH}?person=person.exact_42`, 'en', state.client)
    await waitFor(() =>
      expect(wrapper.find('.snapshot-record-detail [role="alert"]').exists()).toBe(true),
    )
    expect(wrapper.get('main').text()).not.toContain('Wrong identity must stay hidden')
    expect(wrapper.find('.snapshot-record-detail .record').exists()).toBe(false)
  },
)

it.each(['account', 'snapshot'] as const)(
  'clears the previous raw record while a new %s scope is loading',
  async (scope) => {
    const next = deferredResponse()
    let changed = false
    const state = server((request) => {
      const path = new URL(request.url).pathname
      if (changed && (path === API_PATH || path === `/api/v1/snapshots/${OTHER_SNAPSHOT_ID}`))
        return next.promise
      return undefined
    })
    const wrapper = await mountApplicationAt(`${PATH}?person=person.exact_42`, 'en', state.client)
    await waitFor(() =>
      expect(wrapper.get('main').text()).toContain('Source note for person.exact_42'),
    )
    changed = true
    if (scope === 'account') useSessionStore().user = { ...USER, id: 'another-user' }
    else
      await wrapper.vm.$router.push(
        `/projects/${PROJECT_ID}/snapshots/${OTHER_SNAPSHOT_ID}?person=person.exact_42`,
      )
    await flushPromises()
    expect(wrapper.get('main').text()).not.toContain('Source note for person.exact_42')
    expect(wrapper.find('.snapshot-record-detail .record').exists()).toBe(false)
    next.resolve(failure(404))
    await waitFor(() => expect(wrapper.find('main [role="alert"]').exists()).toBe(true))
    expect(wrapper.get('main').text()).not.toContain('Source note for person.exact_42')
  },
)

it.each([500, 403])(
  'keeps evidence on a transient refresh failure and clears denied evidence (%s)',
  async (status) => {
    let failRefresh = false
    const state = server((request) => {
      const path = new URL(request.url).pathname
      if (
        failRefresh &&
        (path === `${API_PATH}/source-members` || path === `${API_PATH}/people/person.exact_42`)
      )
        return failure(status)
      return undefined
    })
    const wrapper = await mountApplicationAt(`${PATH}?person=person.exact_42`, 'en', state.client)
    await waitFor(() => {
      expect(wrapper.get('.snapshot-source-table').text()).toContain('register.xml')
      expect(wrapper.get('.snapshot-record-detail .record').text()).toContain(
        'Source note for person.exact_42',
      )
    })
    const queryClient = wrapper.vm.$.appContext.app.runWithContext(() => useQueryClient())
    failRefresh = true
    await Promise.all([
      queryClient.refetchQueries({
        queryKey: ['snapshots', SNAPSHOT_ID, 'source-members', USER.id],
        exact: true,
      }),
      queryClient.refetchQueries({
        queryKey: ['imported-person', USER.id, PROJECT_ID, SNAPSHOT_ID, 'person.exact_42'],
        exact: true,
      }),
    ])
    await waitFor(() => {
      expect(wrapper.find('.snapshot-sources [role="alert"]').exists()).toBe(true)
      expect(wrapper.find('.snapshot-record-detail [role="alert"]').exists()).toBe(true)
    })
    expect(wrapper.find('.snapshot-source-table').exists()).toBe(status === 500)
    expect(wrapper.find('.snapshot-record-detail .record').exists()).toBe(status === 500)
    expect(wrapper.get('.snapshot-sources').text().includes('register.xml')).toBe(status === 500)
    expect(
      wrapper.get('.snapshot-record-detail').text().includes('Source note for person.exact_42'),
    ).toBe(status === 500)
  },
)

it('moves focus out of record controls hidden by a responsive layout change', async () => {
  const observers: TestResizeObserver[] = []
  class TestResizeObserver implements ResizeObserver {
    readonly targets = new Set<Element>()
    private readonly callback: ResizeObserverCallback
    constructor(callback: ResizeObserverCallback) {
      this.callback = callback
      observers.push(this)
    }
    observe(target: Element): void {
      this.targets.add(target)
    }
    unobserve(target: Element): void {
      this.targets.delete(target)
    }
    disconnect(): void {
      this.targets.clear()
    }
    notify(): void {
      this.callback([], this)
    }
  }
  vi.stubGlobal('ResizeObserver', TestResizeObserver)
  const state = server((request) =>
    new URL(request.url).pathname === `${API_PATH}/people`
      ? page([person(), person('person.second')], 'next-page')
      : undefined,
  )
  const wrapper = await mountApplicationAt(`${PATH}?person=person.exact_42`, 'en', state.client)
  await waitFor(() => expect(wrapper.find('.snapshot-record-detail .record').exists()).toBe(true))
  const action = wrapper.findAll<HTMLElement>('.snapshot-record-row .snapshot-record-view')[1]!
  const row = wrapper.findAll<HTMLElement>('.snapshot-record-row')[1]!
  action.element.focus()
  for (const observer of observers) observer.notify()
  await flushPromises()
  expect(document.activeElement).toBe(action.element)

  // jsdom has no container-query layout; emulate its computed hidden-row result on resize.
  row.element.style.display = 'none'
  for (const observer of observers) observer.notify()
  await waitFor(() =>
    expect(document.activeElement).toBe(wrapper.get('#snapshot-record-detail-panel').element),
  )
  const panel = wrapper.get<HTMLElement>('#snapshot-record-detail-panel')
  panel.element.focus()
  for (const observer of observers) observer.notify()
  await flushPromises()
  expect(document.activeElement).toBe(panel.element)

  row.element.style.display = ''
  const pagination = wrapper.get<HTMLElement>('.snapshot-record-pagination')
  const more = wrapper.get<HTMLElement>('.snapshot-records-more')
  more.element.focus()
  pagination.element.style.display = 'none'
  for (const observer of observers) observer.notify()
  await waitFor(() => expect(document.activeElement).toBe(panel.element))
})
