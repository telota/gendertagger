import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient, type ApiClient } from '@/api'
import AppBreadcrumbs from '@/app/AppBreadcrumbs.vue'
import { createAppI18n, type AppLocale } from '@/app/i18n'
import { createQueryClient } from '@/app/queryClient'
import { createAppRouter } from '@/app/router'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore } from '@/stores/session'

import { apiClientWithRoutes } from '../helpers/api'
import { expectNoAxeViolations } from '../helpers/axe'
import { waitFor } from '../helpers/wait'

const catalogues = { de, en } as const
const PROJECT = 'b0000000-0000-0000-0000-000000000001'
const NEXT = 'b0000000-0000-0000-0000-000000000002'
const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer', roles: [] }
const NAME = 'Personenregister der Berlin-Brandenburgischen Akademie der Wissenschaften'
const project = (id = PROJECT, name = NAME) => ({
  id,
  slug: 'register',
  display_name: name,
  current_user_role: 'viewer',
  working_aggregation_execution_id: null,
  created_at: '2026-01-01T00:00:00Z',
})
const mounted: VueWrapper[] = []

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.replaceChildren()
})

async function render(path: string, locale: AppLocale, client?: ApiClient) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  let session!: ReturnType<typeof useSessionStore>
  const queryClient = createQueryClient()
  const wrapper = mount(
    defineComponent({
      setup() {
        session = useSessionStore()
        session.user = USER
        session.status = 'ready'
        return () => h(AppBreadcrumbs)
      },
    }),
    {
      attachTo: document.body,
      global: {
        plugins: [createPinia(), createAppI18n(locale), router, [VueQueryPlugin, { queryClient }]],
        provide: {
          [API_CLIENT_KEY as symbol]:
            client ??
            apiClientWithRoutes({
              [`/api/v1/projects/${PROJECT}`]: { body: project() },
            }),
        },
      },
    },
  )
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, router, session, queryClient }
}

describe.each(['de', 'en'] as const)('header breadcrumbs in %s', (locale) => {
  const messages = catalogues[locale]

  it('shows a full authorized project and a short review trail without scientific identifiers', async () => {
    const { wrapper } = await render(
      `/projects/${PROJECT}/runs/run-id/aggregations/aggregation-id/review?person=tei-id`,
      locale,
    )
    await waitFor(() => expect(wrapper.findAll('a')).toHaveLength(2))
    expect(wrapper.get('nav').attributes('aria-label')).toBe(messages.breadcrumbs.label)
    const links = wrapper.findAll('a')
    expect(links[0]?.attributes('href')).toBe('/')
    expect(links[1]?.text()).toBe(NAME)
    expect(links[1]?.attributes('href')).toBe(`/projects/${PROJECT}/overview`)
    expect(wrapper.get('[aria-current="page"]').text()).toBe(messages.review.title)
    expect(wrapper.findAll('li')).toHaveLength(3)
    for (const id of [PROJECT, 'run-id', 'aggregation-id', 'tei-id'])
      expect(wrapper.text()).not.toContain(id)
    expect(wrapper.find('h1').exists()).toBe(false)
    await expectNoAxeViolations(wrapper.element)
  })

  it('links only route-supplied parent collections on detail routes', async () => {
    const { wrapper, router } = await render(
      `/projects/${PROJECT}/runs/run-id/exports/export-id`,
      locale,
    )
    await waitFor(() => expect(wrapper.findAll('a')).toHaveLength(3))
    expect(wrapper.findAll('a')[2]?.attributes('href')).toBe(
      `/projects/${PROJECT}/runs/run-id/exports`,
    )
    expect(wrapper.get('[aria-current="page"]').text()).toBe(messages.export.detail.title)
    await router.push(`/projects/${PROJECT}/runs/run-id/evaluations/evaluation-id`)
    expect(wrapper.findAll('a')[2]?.attributes('href')).toBe(
      `/projects/${PROJECT}/runs/run-id/evaluations`,
    )
    await router.push(`/projects/${PROJECT}/snapshots/snapshot-id/runs/run-id`)
    expect(wrapper.findAll('a')[2]?.attributes('href')).toBe(
      `/projects/${PROJECT}/snapshots/snapshot-id/runs`,
    )
    await router.push(`/projects/${PROJECT}/runs/run-id/aggregations/aggregation-id`)
    expect(wrapper.findAll('a')).toHaveLength(2)
  })

  it('does not link back to the exports list from an export in guided mode (D27)', async () => {
    const client = apiClientWithRoutes({
      [`/api/v1/projects/${PROJECT}`]: { body: project() },
      '/api/v1/me/preferences': {
        body: {
          locale: null,
          theme: 'system',
          desktop_sidebar_collapsed: false,
          interface_mode: 'guided',
          revision: 1,
        },
      },
    })
    const { wrapper, router } = await render(
      `/projects/${PROJECT}/runs/run-id/exports/export-id`,
      locale,
      client,
    )
    await waitFor(() => expect(wrapper.findAll('a')).toHaveLength(2))
    expect(wrapper.findAll('a').map((link) => link.attributes('href'))).toEqual([
      '/',
      `/projects/${PROJECT}/gender-tagging`,
    ])
    expect(wrapper.get('[aria-current="page"]').text()).toBe(messages.export.detail.title)

    // Evaluations is its own guided-mode sidebar tab (unlike the exports list), so its detail page
    // keeps a parent crumb back to it, exactly as in advanced mode.
    await router.push(`/projects/${PROJECT}/runs/run-id/evaluations/evaluation-id`)
    expect(wrapper.findAll('a')[2]?.attributes('href')).toBe(
      `/projects/${PROJECT}/runs/run-id/evaluations`,
    )
  })

  it('links the run hierarchy for a method-results page without resolving extra resources', async () => {
    const { wrapper } = await render(
      '/projects/' + PROJECT + '/snapshots/snapshot-id/runs/run-id/executions/execution-id/results',
      locale,
    )
    await waitFor(() => expect(wrapper.findAll('a')).toHaveLength(4))
    expect(wrapper.findAll('a').map((link) => link.attributes('href'))).toEqual([
      '/',
      '/projects/' + PROJECT + '/overview',
      '/projects/' + PROJECT + '/snapshots/snapshot-id/runs',
      '/projects/' + PROJECT + '/snapshots/snapshot-id/runs/run-id',
    ])
    expect(wrapper.get('[aria-current="page"]').text()).toBe(messages.runs.results.title)
    expect(wrapper.text()).not.toContain('execution-id')
  })

  it('links Data as the parent of imported data and import without reading scientific resources', async () => {
    const requests: string[] = []
    const client = createApiClient({
      fetch: (request) => {
        requests.push(new URL(request.url).pathname)
        return Promise.resolve(Response.json(project()))
      },
    })
    const { wrapper, router } = await render(`/projects/${PROJECT}/snapshots`, locale, client)
    await waitFor(() => expect(wrapper.get('[aria-current="page"]').text()).toBe(messages.nav.data))
    expect(wrapper.findAll('a').map((link) => link.attributes('href'))).toEqual([
      '/',
      `/projects/${PROJECT}/overview`,
    ])
    await router.push(`/projects/${PROJECT}/snapshots/snapshot-id?person=record-id`)
    expect(wrapper.findAll('a').map((link) => link.attributes('href'))).toEqual([
      '/',
      `/projects/${PROJECT}/overview`,
      `/projects/${PROJECT}/snapshots`,
    ])
    expect(wrapper.get('[aria-current="page"]').text()).toBe(messages.data.detailTitle)
    expect(wrapper.text()).not.toContain('snapshot-id')
    expect(wrapper.text()).not.toContain('record-id')
    await router.push(`/projects/${PROJECT}/import`)
    expect(wrapper.findAll('a')[2]?.text()).toBe(messages.nav.data)
    expect(wrapper.get('[aria-current="page"]').text()).toBe(messages.nav.import)
    expect(requests).toEqual([`/api/v1/projects/${PROJECT}`, '/api/v1/me/preferences'])
    await expectNoAxeViolations(wrapper.element)
  })

  it('uses the project as current overview, linked back to the home page (D26), and drops context on global routes', async () => {
    const { wrapper, router } = await render(`/projects/${PROJECT}/overview`, locale)
    await waitFor(() => expect(wrapper.text()).toContain(NAME))
    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.get('a').attributes('href')).toBe('/')
    expect(wrapper.get('[aria-current="page"]').text()).toBe(NAME)
    for (const path of ['/settings', '/admin/users', '/projects', '/impressum']) {
      await router.push(path)
      expect(wrapper.text()).not.toContain(NAME)
      expect(wrapper.findAll('li')).toHaveLength(1)
      expect(wrapper.find('a').exists()).toBe(false)
    }
  })

  it('leads back to Gender taggen, not Übersicht, in guided mode (D26/D27)', async () => {
    const client = apiClientWithRoutes({
      [`/api/v1/projects/${PROJECT}`]: { body: project() },
      '/api/v1/me/preferences': {
        body: {
          locale: null,
          theme: 'system',
          desktop_sidebar_collapsed: false,
          interface_mode: 'guided',
          revision: 1,
        },
      },
    })
    const { wrapper, router } = await render(`/projects/${PROJECT}/gender-tagging`, locale, client)
    await waitFor(() => expect(wrapper.text()).toContain(NAME))
    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.get('a').attributes('href')).toBe('/')
    expect(wrapper.get('[aria-current="page"]').text()).toBe(NAME)

    await router.push(`/projects/${PROJECT}/runs/run-id/aggregations/aggregation-id/review`)
    await waitFor(() =>
      expect(wrapper.get('[aria-current="page"]').text()).toBe(messages.review.title),
    )
    const links = wrapper.findAll('a')
    expect(links[1]?.text()).toBe(NAME)
    expect(links[1]?.attributes('href')).toBe(`/projects/${PROJECT}/gender-tagging`)
  })

  it('shows loading instead of the old identity during a project change', async () => {
    let finish!: (value: Response) => void
    const pending = new Promise<Response>((resolve) => (finish = resolve))
    const client = createApiClient({
      fetch: (request) =>
        new URL(request.url).pathname.endsWith(NEXT)
          ? pending
          : Promise.resolve(Response.json(project())),
    })
    const { wrapper, router } = await render(`/projects/${PROJECT}/overview`, locale, client)
    await waitFor(() => expect(wrapper.text()).toContain(NAME))
    await router.push(`/projects/${NEXT}/overview`)
    expect(wrapper.text()).not.toContain(NAME)
    expect(wrapper.text()).toContain(messages.breadcrumbs.projectLoading)
    expect(wrapper.get('nav').attributes('aria-busy')).toBe('true')
    finish(Response.json(project(NEXT, 'Next project')))
    await waitFor(() => expect(wrapper.text()).toContain('Next project'))
    expect(wrapper.get('nav').attributes('aria-busy')).toBeUndefined()
  })

  it('offers retry for read failures without presenting a project chooser', async () => {
    let attempts = 0
    const client = createApiClient({
      fetch: () => {
        attempts += 1
        return Promise.resolve(
          attempts === 1
            ? Response.json(
                { error: { code: 'network_error', message: 'Unavailable' } },
                { status: 503 },
              )
            : Response.json(project()),
        )
      },
    })
    const { wrapper } = await render(`/projects/${PROJECT}/overview`, locale, client)
    await waitFor(() => expect(wrapper.find('button').exists()).toBe(true))
    expect(wrapper.text()).toContain(messages.breadcrumbs.projectLoadError)
    expect(wrapper.find('.project-switcher').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    await waitFor(() => expect(wrapper.text()).toContain(NAME))
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('clears cached identity after permission loss while preserving management-only scope', async () => {
    let denied = false
    const client = createApiClient({
      fetch: () =>
        Promise.resolve(
          denied
            ? Response.json(
                { error: { code: 'resource_not_found', message: 'Missing' } },
                { status: 404 },
              )
            : Response.json(project()),
        ),
    })
    const { wrapper, router, queryClient } = await render(
      `/projects/${PROJECT}/overview`,
      locale,
      client,
    )
    await waitFor(() => expect(wrapper.text()).toContain(NAME))
    denied = true
    await queryClient.invalidateQueries({ queryKey: ['projects', PROJECT] })
    await waitFor(() => expect(wrapper.text()).not.toContain(NAME))
    expect(wrapper.text()).toContain(messages.breadcrumbs.projectAccessUnavailable)
    expect(wrapper.get('.app-breadcrumb-error a').attributes('href')).toBe('/projects')
    await router.push(`/projects/${PROJECT}/members`)
    expect(wrapper.get('[aria-current="page"]').text()).toBe(messages.projectMembers.title)
    expect(wrapper.findAll('a')[1]?.attributes('href')).toBe('/projects')
    expect(wrapper.text()).not.toContain(messages.breadcrumbs.projectAccessUnavailable)
  })

  it('withholds old identity during an account change or password-required session', async () => {
    let nextAccount = false
    let finish!: (value: Response) => void
    const client = createApiClient({
      fetch: () =>
        nextAccount
          ? new Promise<Response>((resolve) => (finish = resolve))
          : Promise.resolve(Response.json(project())),
    })
    const { wrapper, session } = await render(`/projects/${PROJECT}/overview`, locale, client)
    await waitFor(() => expect(wrapper.text()).toContain(NAME))
    nextAccount = true
    session.user = { ...USER, id: 'another-account' }
    await flushPromises()
    expect(wrapper.text()).not.toContain(NAME)
    finish(
      Response.json({ error: { code: 'resource_not_found', message: 'Missing' } }, { status: 404 }),
    )
    await flushPromises()
    expect(wrapper.text()).not.toContain(NAME)
    session.mustChangePassword = true
    await flushPromises()
    expect(wrapper.findAll('li')).toHaveLength(1)
    expect(wrapper.find('a').exists()).toBe(false)
  })
})
