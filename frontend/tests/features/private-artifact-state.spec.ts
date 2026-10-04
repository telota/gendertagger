import { createHash, webcrypto } from 'node:crypto'

import type { QueryClient } from '@tanstack/vue-query'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createApiClient, type components } from '@/api'
import * as queryClients from '@/app/queryClient'
import { useSessionStore } from '@/stores/session'

import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'
import seedReport from './evaluation/fixtures/seed-report.json'

type Account = 'a' | 'b'
type ArtifactKind = 'export' | 'evaluation'
type Application = Awaited<ReturnType<typeof mountApplicationAt>>

const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
const RUN_ID = 'd0000000-0000-0000-0000-000000000001'
const AGG_ID = 'f0000000-0000-0000-0000-000000000001'
const EXPORT_ID = 'e2000000-0000-0000-0000-000000000001'
const EVALUATION_ID = 'e1000000-0000-0000-0000-000000000001'
const EXECUTION_ID = 'd1000000-0000-0000-0000-000000000001'
const USERS = {
  a: { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Account A', roles: [] },
  b: { id: 'a0000000-0000-0000-0000-000000000002', display_name: 'Account B', roles: [] },
} satisfies Record<Account, components['schemas']['CurrentUser']>

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function denied(status: number): Response {
  return jsonResponse(
    { error: { code: 'resource_not_found', message: 'Unavailable', details: {}, request_id: 'r' } },
    { status },
  )
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((finish) => {
    resolve = finish
  })
  return { promise, resolve }
}

function output(account: Account): string {
  return `<TEI xmlns="http://www.tei-c.org/ns/1.0"><text>private-${account}-output</text></TEI>`
}

function outputSha(account: Account): string {
  return createHash('sha256').update(output(account)).digest('hex')
}

function detail(kind: ArtifactKind, account: Account) {
  const common = {
    run_id: RUN_ID,
    aggregation_execution_id: AGG_ID,
    status: 'completed',
    created_at: '2026-01-01T12:00:00Z',
    started_at: '2026-01-01T12:00:01Z',
    finished_at: '2026-01-01T12:00:05Z',
    failure_class: null,
    failure_diagnostic: null,
  }
  return kind === 'export'
    ? {
        ...common,
        id: EXPORT_ID,
        format: 'tei',
        label_source_policy: 'human_overrides',
        tei_profile: 'tei_p5_gender_v1',
        human_resp_id: `#private-${account}-provenance`,
        manifest_artifact_id: `manifest-${account}`,
      }
    : {
        ...common,
        id: EVALUATION_ID,
        definition: 'gnd_benchmark_v1',
        config_sha256: (account === 'a' ? '8' : '9').repeat(64),
        resolved_config: { confidence_level: 0.95, source: `private-${account}-provenance` },
        method_execution_ids: [EXECUTION_ID],
        report_artifact_id: `report-${account}`,
      }
}

function artifact(kind: ArtifactKind, account: Account) {
  if (kind === 'evaluation') {
    return {
      ...seedReport,
      benchmark: { ...seedReport.benchmark, method_name: `private-${account}-benchmark` },
    }
  }
  return {
    version: 1,
    export_execution_id: EXPORT_ID,
    dataset_snapshot_id: SNAPSHOT_ID,
    source_snapshot_sha256: account.repeat(64),
    run_id: RUN_ID,
    aggregation_execution_id: AGG_ID,
    format: 'tei',
    label_source_policy: 'human_overrides',
    tei_profile: 'tei_p5_gender_v1',
    outputs: [
      {
        logical_name: `private-${account}.xml`,
        sha256: outputSha(account),
        byte_size: new TextEncoder().encode(output(account)).length,
        media_type: 'application/tei+xml',
      },
    ],
    generated_at: '2026-01-01T12:00:05Z',
  }
}

function paths(kind: ArtifactKind) {
  const plural = kind === 'export' ? 'exports' : 'evaluations'
  const id = kind === 'export' ? EXPORT_ID : EVALUATION_ID
  const list = `/projects/${PROJECT_ID}/runs/${RUN_ID}/${plural}`
  const apiDetail = `/api/v1/${plural}/${id}`
  return {
    list,
    detail: `${list}/${id}`,
    apiDetail,
    artifact: `${apiDetail}/${kind === 'export' ? 'manifest' : 'report'}`,
  }
}

interface Server {
  account: Account
  detailStatus: number
  artifactStatus: number
  artifactAccount?: Account
  nextArtifact?: Promise<Response>
  nextDownload?: Promise<Response>
  requests: { account: Account; path: string }[]
}

function newServer(): Server {
  return { account: 'a', detailStatus: 200, artifactStatus: 200, requests: [] }
}

function clientFor(server: Server) {
  return createApiClient({
    fetch: async (request) => {
      const { pathname } = new URL(request.url)
      const account = server.account
      server.requests.push({ account, path: pathname })
      if (pathname === '/api/v1/branding') return jsonResponse({})
      if (pathname === '/api/v1/me') return jsonResponse(USERS[account])
      if (pathname === '/api/v1/auth/login') {
        const body = (await request.json()) as { username: Account }
        server.account = body.username
        return jsonResponse(USERS[server.account])
      }
      if (pathname === '/api/v1/auth/logout') return new Response(null, { status: 204 })
      if (pathname === '/api/v1/auth/session') {
        return jsonResponse({ must_change_password: false, keep_signed_in: false })
      }
      if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
        return jsonResponse({
          id: PROJECT_ID,
          slug: 'private-project',
          display_name: 'Private project',
          description: null,
          team: {
            id: 'b1000000-0000-0000-0000-000000000001',
            slug: 'team',
            display_name: 'Team',
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
          manager_user_id: USERS.a.id,
          created_by_user_id: USERS.a.id,
          current_user_role: 'operator',
          current_user_can_manage_members: false,
          game_mode_enabled: false,
          created_at: '2026-01-01T00:00:00Z',
        } satisfies components['schemas']['AccessibleProject'])
      }
      if (pathname === `/api/v1/runs/${RUN_ID}`) {
        return jsonResponse({
          id: RUN_ID,
          dataset_snapshot_id: SNAPSHOT_ID,
          status: 'completed',
          created_at: '2026-01-01T10:00:00Z',
          config_sha256: 'd'.repeat(64),
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
          source_artifact_id: 'source',
          source_sha256: 'd'.repeat(64),
          parser_version: '1',
          status: 'ready',
          record_count: 7,
          import_config: { source_format: 'tei', packaging: 'single' },
          created_at: '2026-01-01T00:00:00Z',
        })
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/executions`) {
        return jsonResponse([
          {
            id: EXECUTION_ID,
            run_id: RUN_ID,
            method_name: 'gnd',
            status: 'completed',
            implementation_version: 'gnd_v1',
            normalization_version: 'gnd_v1',
            completed_count: 7,
            failed_count: 0,
            total_count: 7,
            progress: { completed: 7, failed: 0, total: 7, percentage: 100 },
            config_sha256: 'd'.repeat(64),
            resolved_config: {},
            created_at: '2026-01-01T00:00:00Z',
          },
        ])
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/aggregations`) {
        return jsonResponse({
          items: [
            {
              id: AGG_ID,
              run_id: RUN_ID,
              strategy: 'reference_v1',
              status: 'completed',
              resolved_config: {},
              method_execution_ids: [],
              config_sha256: 'd'.repeat(64),
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
          next_cursor: null,
          has_more: false,
        })
      }
      for (const kind of ['export', 'evaluation'] as const) {
        const route = paths(kind)
        if (
          pathname === `/api/v1/runs/${RUN_ID}/${kind === 'export' ? 'exports' : 'evaluations'}`
        ) {
          return jsonResponse({ items: [], next_cursor: null, has_more: false })
        }
        if (pathname === route.apiDetail) {
          return server.detailStatus === 200
            ? jsonResponse(detail(kind, account))
            : denied(server.detailStatus)
        }
        if (pathname === route.artifact) {
          if (server.nextArtifact) {
            const response = server.nextArtifact
            delete server.nextArtifact
            return response
          }
          return server.artifactStatus === 200
            ? jsonResponse(artifact(kind, server.artifactAccount ?? account))
            : denied(server.artifactStatus)
        }
      }
      if (pathname === `${paths('export').apiDetail}/download`) {
        if (server.nextDownload) {
          const response = server.nextDownload
          delete server.nextDownload
          return response
        }
        return new Response(output(account), { headers: { 'content-type': 'application/tei+xml' } })
      }
      return denied(404)
    },
  })
}

function cachedData(cache: QueryClient): string {
  return JSON.stringify(
    cache
      .getQueryCache()
      .getAll()
      .map((query) => query.state.data),
  )
}

async function login(account: Account): Promise<void> {
  await useSessionStore().login({ username: account, password: 'secret', keepSignedIn: false })
  await flushPromises()
}

async function mountArtifact(kind: ArtifactKind, server: Server) {
  const cache = queryClients.createQueryClient()
  vi.spyOn(queryClients, 'createQueryClient').mockReturnValue(cache)
  const wrapper = await mountApplicationAt(paths(kind).detail, 'en', clientFor(server))
  await waitFor(() => expect(wrapper.find(`.${kind}-detail-facts`).exists()).toBe(true))
  return { wrapper, cache }
}

async function expectArtifact(
  wrapper: Application,
  kind: ArtifactKind,
  account: Account,
): Promise<void> {
  await waitFor(() =>
    expect(wrapper.text()).toContain(
      kind === 'export' ? `private-${account}.xml` : `private-${account}-benchmark`,
    ),
  )
}

async function refetchArtifact(cache: QueryClient, kind: ArtifactKind): Promise<void> {
  await cache.refetchQueries({
    predicate: (query) =>
      query.queryKey[0] === (kind === 'export' ? 'exports' : 'evaluations') &&
      query.queryKey.includes(kind === 'export' ? 'manifest' : 'report'),
  })
  await flushPromises()
}

const saved: string[] = []
beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  URL.createObjectURL = () => 'blob:test'
  URL.revokeObjectURL = () => {}
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push(this.download)
  })
  saved.length = 0
})

afterEach(async () => {
  await flushPromises()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.body.replaceChildren()
})

describe.each(['export', 'evaluation'] as const)(
  '%s artifact ownership in the mounted app',
  (kind) => {
    it.each([403, 404])(
      'refetches detail for a replacement account denied with %s and hides all prior provenance',
      async (status) => {
        const server = newServer()
        const { wrapper, cache } = await mountArtifact(kind, server)
        await expectArtifact(wrapper, kind, 'a')
        const mountedDetail = wrapper.get(`.${kind}-detail`).element

        server.detailStatus = status
        await login('b')
        await waitFor(() =>
          expect(server.requests).toContainEqual({ account: 'b', path: paths(kind).apiDetail }),
        )

        expect(wrapper.get(`.${kind}-detail`).element).toBe(mountedDetail)
        expect(wrapper.text()).not.toContain('private-a')
        expect(wrapper.find(`.${kind}-detail-download`).exists()).toBe(false)
        expect(cachedData(cache)).not.toContain('private-a')
        expect(server.requests).not.toContainEqual({ account: 'b', path: paths(kind).artifact })
      },
    )

    it('fetches and displays only the replacement account’s detail and immutable artifact', async () => {
      const server = newServer()
      const { wrapper, cache } = await mountArtifact(kind, server)
      await expectArtifact(wrapper, kind, 'a')
      const mountedDetail = wrapper.get(`.${kind}-detail`).element

      await login('b')
      await expectArtifact(wrapper, kind, 'b')

      expect(wrapper.get(`.${kind}-detail`).element).toBe(mountedDetail)
      expect(wrapper.text()).toContain('private-b-provenance')
      expect(wrapper.text()).not.toContain('private-a')
      expect(cachedData(cache)).not.toContain('private-a')
      expect(server.requests).toContainEqual({ account: 'b', path: paths(kind).apiDetail })
      expect(server.requests).toContainEqual({ account: 'b', path: paths(kind).artifact })
    })

    it('does not revive a prior artifact after logout and a new login to the same account', async () => {
      const server = newServer()
      const { wrapper, cache } = await mountArtifact(kind, server)
      await expectArtifact(wrapper, kind, 'a')

      await useSessionStore().logout()
      await flushPromises()
      expect(cachedData(cache)).not.toContain('private-a')
      // The identity is the same, but this is a new session ownership after explicit logout.
      server.artifactAccount = 'b'
      await login('a')
      await wrapper.vm.$router.push(paths(kind).detail)
      await expectArtifact(wrapper, kind, 'b')

      expect(wrapper.text()).not.toContain(
        kind === 'export' ? 'private-a.xml' : 'private-a-benchmark',
      )
      expect(
        server.requests.filter((request) => request.path === paths(kind).artifact),
      ).toHaveLength(2)
    })

    it('drops a delayed old-account artifact response after replacement', async () => {
      const pending = deferred<Response>()
      const server = newServer()
      server.nextArtifact = pending.promise
      const { wrapper, cache } = await mountArtifact(kind, server)
      await waitFor(() =>
        expect(server.requests).toContainEqual({ account: 'a', path: paths(kind).artifact }),
      )

      await login('b')
      await expectArtifact(wrapper, kind, 'b')
      pending.resolve(jsonResponse(artifact(kind, 'a')))
      await flushPromises()

      expect(wrapper.text()).not.toContain('private-a')
      expect(cachedData(cache)).not.toContain('private-a')
      await expectArtifact(wrapper, kind, 'b')
    })

    it.each([403, 404])(
      'hides a prior immutable artifact when refetch loses access with %s',
      async (status) => {
        const server = newServer()
        const { wrapper, cache } = await mountArtifact(kind, server)
        await expectArtifact(wrapper, kind, 'a')

        server.artifactStatus = status
        await refetchArtifact(cache, kind)

        expect(wrapper.text()).not.toContain(
          kind === 'export' ? 'private-a.xml' : 'private-a-benchmark',
        )
      },
    )

    it('preserves the same account’s immutable artifact while session readiness recovers', async () => {
      const server = newServer()
      const { wrapper } = await mountArtifact(kind, server)
      await expectArtifact(wrapper, kind, 'a')
      const revision = useSessionStore().principalRevision

      useSessionStore().status = 'loading'
      await flushPromises()
      expect(wrapper.text()).not.toContain('private-a')
      await login('a')
      await expectArtifact(wrapper, kind, 'a')

      expect(useSessionStore().principalRevision).toBe(revision)
      expect(
        server.requests.filter((request) => request.path === paths(kind).artifact),
      ).toHaveLength(1)
    })

    it('keeps an unsaved creation draft during same-account session recovery', async () => {
      const server = newServer()
      const wrapper = await mountApplicationAt(paths(kind).list, 'en', clientFor(server))
      await waitFor(() => expect(wrapper.find(`.${kind}-list-create`).exists()).toBe(true))
      await wrapper.get(`.${kind}-list-create`).trigger('click')
      const input = kind === 'export' ? '#export-resp' : `#evaluate-${EXECUTION_ID}`
      await waitFor(() => expect(wrapper.find(input).exists()).toBe(true))
      await wrapper.get(input).setValue(kind === 'export' ? '#unsaved-editor' : false)

      await login('a')

      expect(wrapper.find(`.new-${kind}`).exists()).toBe(true)
      const element = wrapper.get<HTMLInputElement>(input).element
      expect(kind === 'export' ? element.value : element.checked).toBe(
        kind === 'export' ? '#unsaved-editor' : false,
      )
    })
  },
)

describe('export download state ownership in the mounted app', () => {
  it('does not save or display a delayed download from the replaced account', async () => {
    const server = newServer()
    const pending = deferred<Response>()
    server.nextDownload = pending.promise
    const { wrapper } = await mountArtifact('export', server)
    await expectArtifact(wrapper, 'export', 'a')
    await wrapper.get('.export-detail-download').trigger('click')
    await waitFor(() =>
      expect(server.requests).toContainEqual({
        account: 'a',
        path: `${paths('export').apiDetail}/download`,
      }),
    )

    await login('b')
    await expectArtifact(wrapper, 'export', 'b')
    pending.resolve(
      new Response(output('a'), { headers: { 'content-type': 'application/tei+xml' } }),
    )
    await flushPromises()

    expect(saved).toEqual([])
    expect(wrapper.find('.export-detail-result').exists()).toBe(false)
    expect(wrapper.find('#export-expected').exists()).toBe(false)
  })

  it('drops a completed checksum calculation if its account was replaced during hashing', async () => {
    const server = newServer()
    const digest = deferred<ArrayBuffer>()
    const digestStarted = vi.fn(() => digest.promise)
    vi.stubGlobal('crypto', { subtle: { digest: digestStarted } })
    const { wrapper } = await mountArtifact('export', server)
    await expectArtifact(wrapper, 'export', 'a')
    await wrapper.get('.export-detail-download').trigger('click')
    await waitFor(() => expect(digestStarted).toHaveBeenCalledOnce())

    await login('b')
    await expectArtifact(wrapper, 'export', 'b')
    digest.resolve(new Uint8Array(32).buffer)
    await flushPromises()

    expect(saved).toEqual([])
    expect(wrapper.find('.export-detail-result').exists()).toBe(false)
  })

  it.each(['replacement', 'access denial'] as const)(
    'clears the saved result and expected checksum after %s',
    async (loss) => {
      const server = newServer()
      const { wrapper, cache } = await mountArtifact('export', server)
      await expectArtifact(wrapper, 'export', 'a')
      await wrapper.get('.export-detail-download').trigger('click')
      await waitFor(() => expect(wrapper.find('#export-expected').exists()).toBe(true))
      await wrapper.get('#export-expected').setValue('c'.repeat(64))
      expect(saved).toHaveLength(1)

      if (loss === 'replacement') {
        await login('b')
        await expectArtifact(wrapper, 'export', 'b')
      } else {
        server.artifactStatus = 403
        await refetchArtifact(cache, 'export')
        server.artifactStatus = 200
        await refetchArtifact(cache, 'export')
        await expectArtifact(wrapper, 'export', 'a')
      }

      expect(wrapper.find('.export-detail-result').exists()).toBe(false)
      await wrapper.get('.export-detail-download').trigger('click')
      await waitFor(() => expect(wrapper.find('#export-expected').exists()).toBe(true))
      expect(wrapper.get<HTMLInputElement>('#export-expected').element.value).toBe('')
      expect(wrapper.get('.export-detail-result .export-detail-hash').text()).toBe(
        outputSha(loss === 'replacement' ? 'b' : 'a'),
      )
    },
  )

  it('preserves the completed download and expected checksum during same-account recovery', async () => {
    const server = newServer()
    const { wrapper } = await mountArtifact('export', server)
    await expectArtifact(wrapper, 'export', 'a')
    await wrapper.get('.export-detail-download').trigger('click')
    await waitFor(() => expect(wrapper.find('#export-expected').exists()).toBe(true))
    await wrapper.get('#export-expected').setValue(outputSha('a'))

    useSessionStore().status = 'loading'
    await flushPromises()
    expect(wrapper.find('.export-detail-result').exists()).toBe(false)
    await login('a')
    await waitFor(() => expect(wrapper.find('#export-expected').exists()).toBe(true))

    expect(wrapper.get<HTMLInputElement>('#export-expected').element.value).toBe(outputSha('a'))
    expect(wrapper.get('.export-detail-result .export-detail-hash').text()).toBe(outputSha('a'))
    expect(saved).toHaveLength(1)
  })
})
