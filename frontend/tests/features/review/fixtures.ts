import { createApiClient } from '@/api'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

export function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

export const catalogues = { de, en } as const
const USER = { id: 'a0000000-0000-0000-0000-000000000002', display_name: 'Op', roles: [] }
export const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
export const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
export const RUN_ID = 'd0000000-0000-0000-0000-000000000001'
export const AGG_ID = 'f0000000-0000-0000-0000-000000000001'

export function item(tei: string, extra: Record<string, unknown> = {}) {
  return {
    aggregation_execution_id: AGG_ID,
    aggregated_result_id: `r-${tei}`,
    snapshot_id: SNAPSHOT_ID,
    person_record_id: `p-${tei}`,
    tei_id: tei,
    surname: `Surname-${tei}`,
    forenames: ['Given'],
    aggregation_outcome: 'decided',
    machine_label: 'male',
    final_label: 'male',
    agreement_tier: 'weak_majority',
    certainty_tier: 'low',
    override_source: null,
    has_authority_conflict: false,
    has_prediction_error: false,
    workflow_state: 'unreviewed',
    review_revision: 0,
    current_annotation_id: null,
    selected_method_result: null,
    ...extra,
  }
}

export const SUMMARY = {
  aggregation_execution_id: AGG_ID,
  result_count: 9,
  last_annotated_at: null,
  groups: [
    {
      certainty_tier: 'high',
      agreement_tier: 'unanimous',
      workflow_state: 'unreviewed',
      final_label: 'male',
      review_action: null,
      result_count: 4,
    },
    {
      certainty_tier: 'low',
      agreement_tier: 'weak_majority',
      workflow_state: 'unreviewed',
      final_label: 'male',
      review_action: null,
      result_count: 2,
    },
    {
      certainty_tier: 'contested',
      agreement_tier: 'no_consensus',
      workflow_state: 'reviewed',
      final_label: 'female',
      review_action: 'correct',
      result_count: 1,
    },
    {
      certainty_tier: 'single',
      agreement_tier: 'single_rater',
      workflow_state: 'unreviewed',
      final_label: 'institution',
      review_action: null,
      result_count: 2,
    },
  ],
}

export const PREDICTIONS = [
  {
    method_execution_id: 'x1',
    method_name: 'gnd',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: 'pr1',
    prediction: {
      label: 'female',
      status: 'success',
      method_confidence: null,
      raw_label: 'f',
      raw_output: {},
      metadata: {},
    },
  },
  {
    method_execution_id: 'x2',
    method_name: 'hf_distilbert',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: 'pr2',
    prediction: {
      label: null,
      status: 'error',
      method_confidence: null,
      raw_label: null,
      raw_output: {},
      metadata: {},
    },
  },
  {
    method_execution_id: 'x3',
    method_name: 'gender_guesser',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: 'pr3',
    prediction: {
      label: null,
      status: 'abstain',
      method_confidence: null,
      raw_label: null,
      raw_output: {},
      metadata: {},
    },
  },
  {
    method_execution_id: 'x4',
    method_name: 'local_llm',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: 'pr4',
    prediction: {
      label: 'unknown',
      status: 'success',
      method_confidence: 0.42,
      raw_label: 'unclear',
      raw_output: {},
      metadata: {},
    },
  },
  {
    method_execution_id: 'x5',
    method_name: 'nomquamgender',
    implementation_version: 'v1',
    normalization_version: 'v1',
    prediction_id: null,
    prediction: null,
  },
]

export const HISTORY = {
  snapshot_id: SNAPSHOT_ID,
  person_record_id: 'p',
  tei_id: 'demo-1',
  revision: 2,
  workflow_state: 'reviewed',
  current_annotation_id: 'a2',
  annotations: [
    {
      id: 'a2',
      snapshot_id: SNAPSHOT_ID,
      person_record_id: 'p',
      tei_id: 'demo-1',
      action: 'correct',
      label: 'female',
      reviewer_user_id: 'u',
      reviewer_display_name: 'Jo Reviewer',
      comment: 'Attested as a woman.',
      aggregated_result_id: 'r',
      supersedes_annotation_id: 'a1',
      resulting_revision: 2,
      created_at: '2026-01-02T10:00:00Z',
    },
    {
      id: 'a1',
      snapshot_id: SNAPSHOT_ID,
      person_record_id: 'p',
      tei_id: 'demo-1',
      action: 'defer',
      label: null,
      reviewer_user_id: 'u2',
      reviewer_display_name: 'Sam Reviewer',
      comment: null,
      aggregated_result_id: 'r',
      supersedes_annotation_id: null,
      resulting_revision: 1,
      created_at: '2026-01-01T10:00:00Z',
    },
  ],
}

/** The annotation chain as a test server holds and extends it. */
export interface HistoryFixture {
  revision: number
  annotations: Record<string, unknown>[]
  [key: string]: unknown
}

export interface Server {
  aggregationStatus: string
  /** One entry per request, in order: the query string of `GET /review-items`. */
  requests: URLSearchParams[]
  pages: { items: ReturnType<typeof item>[]; next: string | null }[]
  known: ReturnType<typeof item>[]
  /** The caller's role in the project. */
  role: 'viewer' | 'reviewer' | 'operator'
  /** The person's annotation chain as the server holds it; a successful write extends it. */
  history: HistoryFixture
  /** Bodies of every `POST /annotations` received. */
  posts: Record<string, unknown>[]
  /** Every request that is not a read, as `METHOD path`: the only writes a reviewer may cause. */
  writes: string[]
  /** People whose write is refused with a 409 (somebody else changed them first). */
  conflictTeis: string[]
  /** People whose write fails with a 500. */
  failTeis: string[]
  /** When set, every `POST /annotations` waits for it, so a test can act while a write is in flight. */
  gate: Promise<void> | null
  /** What the next `POST /annotations` answers. */
  postOutcome: 'ok' | 'conflict' | 'forbidden'
}

export function newServer(overrides: Partial<Server> = {}): Server {
  return {
    aggregationStatus: 'completed',
    requests: [],
    pages: [
      {
        items: [
          item('demo-1', {
            override_source: 'gnd',
            certainty_tier: 'contested',
            agreement_tier: 'no_consensus',
          }),
          item('demo-2'),
        ],
        next: null,
      },
    ],
    known: [],
    role: 'reviewer',
    history: structuredClone(HISTORY) as HistoryFixture,
    posts: [],
    writes: [],
    conflictTeis: [],
    failTeis: [],
    gate: null,
    postOutcome: 'ok',
    ...overrides,
  }
}

export function reviewClient(server: Server) {
  return createApiClient({
    fetch: async (request) => {
      const url = new URL(request.url)
      const { pathname } = url
      if (request.method !== 'GET') server.writes.push(`${request.method} ${pathname}`)
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
      if (pathname === '/api/v1/methods') {
        return jsonResponse([
          {
            name: 'gnd',
            implementation_version: 'v1',
            normalization_version: 'v1',
            method_confidence_range: null,
          },
          {
            name: 'local_llm',
            implementation_version: 'v1',
            normalization_version: 'v1',
            method_confidence_range: { minimum: 0, maximum: 1 },
          },
        ])
      }
      if (pathname === `/api/v1/aggregations/${AGG_ID}`) {
        return jsonResponse({
          id: AGG_ID,
          run_id: RUN_ID,
          strategy: 'reference_v1',
          status: server.aggregationStatus,
          resolved_config: {},
          method_execution_ids: [],
          config_sha256: '9'.repeat(64),
          created_at: '2026-01-01T11:00:00Z',
        })
      }
      if (pathname === `/api/v1/aggregations/${AGG_ID}/review-summary`) return jsonResponse(SUMMARY)
      if (pathname === '/api/v1/review-items') {
        server.requests.push(url.searchParams)
        const cursor = url.searchParams.get('cursor')
        const q = url.searchParams.get('q')
        if (q !== null && server.known.length > 0) {
          return jsonResponse({
            items: server.known.filter((i) => i.tei_id === q),
            next_cursor: null,
            has_more: false,
          })
        }
        const index = cursor === null ? 0 : Number(cursor)
        const page = server.pages[index] ?? { items: [], next: null }
        return jsonResponse({
          items: page.items,
          next_cursor: page.next,
          has_more: page.next !== null,
        })
      }
      if (pathname.endsWith('/predictions')) return jsonResponse(PREDICTIONS)
      if (pathname === '/api/v1/annotations' && request.method === 'POST') {
        const body = (await request.json()) as Record<string, unknown>
        server.posts.push(body)
        if (server.gate) await server.gate
        if (server.conflictTeis.includes(body.tei_id as string)) {
          return jsonResponse(
            {
              error: {
                code: 'annotation_conflict',
                message: 'The review state has changed.',
                details: { current_revision: 9 },
                request_id: 'r',
              },
            },
            { status: 409 },
          )
        }
        if (server.failTeis.includes(body.tei_id as string)) {
          return jsonResponse(
            { error: { code: 'internal_error', message: 'boom', details: {}, request_id: 'r' } },
            { status: 500 },
          )
        }
        if (server.postOutcome === 'forbidden') {
          return jsonResponse(
            { error: { code: 'forbidden', message: 'no', details: {}, request_id: 'r' } },
            { status: 403 },
          )
        }
        if (server.postOutcome === 'conflict') {
          // Somebody else got there first: the person moved on and the write is refused.
          const revision = server.history.revision + 1
          server.history = {
            ...server.history,
            revision,
            annotations: [
              {
                ...server.history.annotations[0]!,
                id: `other-${revision}`,
                action: 'correct',
                label: 'institution',
                reviewer_display_name: 'Alex Other',
                resulting_revision: revision,
                comment: null,
              },
              ...server.history.annotations,
            ],
          }
          return jsonResponse(
            {
              error: {
                code: 'annotation_conflict',
                message: 'The review state has changed.',
                details: { current_revision: revision },
                request_id: 'r',
              },
            },
            { status: 409 },
          )
        }
        const revision = server.history.revision + 1
        const created = {
          ...server.history.annotations[0]!,
          id: `new-${revision}`,
          action: body.action as string,
          label: (body.label as string | undefined) ?? null,
          comment: (body.comment as string | undefined) ?? null,
          reviewer_display_name: 'Me Reviewer',
          resulting_revision: revision,
        }
        server.history = {
          ...server.history,
          revision,
          annotations: [created, ...server.history.annotations],
        }
        // The queue's projection follows the decision; the machine result it came from does not.
        for (const page of server.pages) {
          for (const entry of page.items) {
            if (entry.tei_id !== body.tei_id) continue
            entry.review_revision = revision
            entry.workflow_state = body.action === 'defer' ? 'deferred' : 'reviewed'
            if (body.action !== 'defer') entry.final_label = body.label as string
          }
        }
        return jsonResponse(created, { status: 201 })
      }
      if (pathname === '/api/v1/annotations') return jsonResponse(server.history)
      if (pathname.startsWith(`/api/v1/snapshots/${SNAPSHOT_ID}/people/`)) {
        return jsonResponse({
          id: 'p',
          dataset_snapshot_id: SNAPSHOT_ID,
          tei_id: 'demo-1',
          surname: 'S',
          forenames: ['G'],
          birth: '1768',
          death: '1834',
          gnd_id: '118607626',
          note: 'A theologian.',
          created_at: '2026-01-01T00:00:00Z',
        })
      }
      return jsonResponse({}, { status: 404 })
    },
  })
}
