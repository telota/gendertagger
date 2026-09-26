import { createApiClient, type components } from '@/api'

export const PROJECT = 'b0000000-0000-0000-0000-000000000001'
export const SNAPSHOT = 'c0000000-0000-0000-0000-000000000001'
export const OTHER_SNAPSHOT = 'c0000000-0000-0000-0000-000000000002'
export const RUN = 'd0000000-0000-0000-0000-000000000001'
export const OTHER_RUN = 'd0000000-0000-0000-0000-000000000002'
export const RESULT = 'e0000000-0000-0000-0000-000000000001'
export const OTHER_RESULT = 'e0000000-0000-0000-0000-000000000002'

type Snapshot = components['schemas']['DatasetSnapshot']
type Run = components['schemas']['Run']
type Result = components['schemas']['AggregationExecution']
type ProjectReviewResult = components['schemas']['ProjectReviewResult']
type Person = components['schemas']['SnapshotAnnotationItem']
type History = components['schemas']['AnnotationHistory']

export function snapshot(id = SNAPSHOT, extra: Partial<Snapshot> = {}): Snapshot {
  return {
    id,
    project_id: PROJECT,
    status: 'ready',
    record_count: 2,
    parser_version: 'tei_v1',
    source_artifact_id: 'a0000000-0000-0000-0000-000000000001',
    source_sha256: 'a'.repeat(64),
    created_at: id === SNAPSHOT ? '2026-01-02T10:00:00Z' : '2026-01-01T10:00:00Z',
    import_config: { source_format: 'tei' },
    ...extra,
  }
}

export function run(id = RUN, extra: Partial<Run> = {}): Run {
  return {
    id,
    dataset_snapshot_id: SNAPSHOT,
    status: 'completed',
    created_at: id === RUN ? '2026-01-03T10:00:00Z' : '2026-01-03T11:00:00Z',
    resolved_config: { methods: [{ name: 'gender_guesser', enabled: true, config: {} }] },
    progress: { completed: 2, failed: 0, total: 2, percentage: 100 },
    config_sha256: 'c'.repeat(64),
    application_version: '1',
    code_git_commit: 'abc',
    python_version: '3.12',
    ...extra,
  } as Run
}

export function result(id = RESULT, extra: Partial<Result> = {}): Result {
  return {
    id,
    run_id: RUN,
    status: 'completed',
    strategy: 'reference_v1',
    method_execution_ids: ['execution-1'],
    created_at: id === RESULT ? '2026-01-04T10:00:00Z' : '2026-01-04T11:00:00Z',
    config_sha256: 'd'.repeat(64),
    resolved_config: {},
    ...extra,
  } as Result
}

function reviewResult(server: TaskServer, aggregation: Result): ProjectReviewResult {
  const linkedRun =
    server.runOverrides[aggregation.run_id] ??
    server.runPages.flat().find((entry) => entry.id === aggregation.run_id) ??
    run(aggregation.run_id)
  const linkedSnapshot =
    server.snapshotOverrides[linkedRun.dataset_snapshot_id] ??
    server.snapshotPages.flat().find((entry) => entry.id === linkedRun.dataset_snapshot_id) ??
    snapshot(linkedRun.dataset_snapshot_id)
  return {
    id: aggregation.id,
    created_at: aggregation.created_at,
    aggregation,
    run: linkedRun,
    snapshot: linkedSnapshot,
  }
}

export function person(tei = 'demo-1', extra: Partial<Person> = {}): Person {
  return {
    snapshot_id: SNAPSHOT,
    person_record_id: `person-${tei}`,
    tei_id: tei,
    surname: tei === 'demo-1' ? 'Müller' : 'Schmidt',
    forenames: ['Ada'],
    workflow_state: 'unreviewed',
    review_revision: 0,
    current_annotation_id: null,
    human_label: null,
    ...extra,
  }
}

export interface TaskServer {
  role: 'operator' | 'reviewer' | 'viewer'
  workingId: string | null
  gameEnabled: boolean
  snapshotPages: Snapshot[][]
  runPages: Run[][]
  resultPages: Result[][]
  peoplePages: Person[][]
  knownPeople: Person[]
  snapshotOverrides: Record<string, Snapshot>
  runOverrides: Record<string, Run>
  failures: Set<string>
  requests: { method: string; path: string; query: URLSearchParams }[]
  writes: string[]
  posts: components['schemas']['AnnotationCreate'][]
  histories: Record<string, History>
  snapshotGate?: Promise<void>
}

export function taskServer(overrides: Partial<TaskServer> = {}): TaskServer {
  return {
    role: 'reviewer',
    workingId: null,
    gameEnabled: true,
    snapshotPages: [[snapshot()]],
    runPages: [[run()]],
    resultPages: [[result()]],
    peoplePages: [[person()]],
    knownPeople: [person(), person('later-person')],
    snapshotOverrides: {},
    runOverrides: {},
    failures: new Set(),
    requests: [],
    writes: [],
    posts: [],
    histories: {},
    ...overrides,
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function page<T>(pages: T[][], cursor: string | null) {
  const index = cursor ? Number(cursor.slice('page-'.length)) : 0
  const hasMore = index + 1 < pages.length
  return {
    items: pages[index] ?? [],
    has_more: hasMore,
    next_cursor: hasMore ? `page-${index + 1}` : null,
  }
}

export function taskClient(server: TaskServer) {
  return createApiClient({
    fetch: async (request) => {
      const { pathname: path, searchParams: query } = new URL(request.url)
      server.requests.push({ method: request.method, path, query })
      if (request.method !== 'GET') server.writes.push(`${request.method} ${path}`)
      if (server.failures.has(path))
        return json({ error: { code: 'internal_error', message: 'Unavailable', details: {} } }, 500)
      if (path === '/api/v1/branding') return json({})
      if (path === '/api/v1/me') return json({ id: 'user-1', display_name: 'Editor', roles: [] })
      if (path === '/api/v1/auth/session')
        return json({ must_change_password: false, keep_signed_in: false })
      const project = {
        id: PROJECT,
        slug: 'project-a',
        display_name: 'Project A',
        current_user_role: server.role,
        current_user_can_manage_members: false,
        working_aggregation_execution_id: server.workingId,
        game_mode_enabled: server.gameEnabled,
      }
      if (path === '/api/v1/projects') return json(page([[project]], null))
      if (path === `/api/v1/projects/${PROJECT}`) return json(project)
      if (path === `/api/v1/projects/${PROJECT}/data-availability`)
        return json({
          project_id: PROJECT,
          has_ready_snapshots: true,
          has_completed_aggregations: server.resultPages.flat().length > 0,
        })
      if (path === `/api/v1/projects/${PROJECT}/review-results`)
        return json(
          page(
            server.resultPages.map((entries) =>
              entries.map((entry) => reviewResult(server, entry)),
            ),
            query.get('cursor'),
          ),
        )
      if (path === `/api/v1/projects/${PROJECT}/snapshots`)
        return json(page(server.snapshotPages, query.get('cursor')))
      const segments = path.split('/').map(decodeURIComponent)
      if (segments[3] === 'snapshots') {
        const id = segments[4] ?? ''
        if (segments.length === 5) {
          if (server.snapshotGate) await server.snapshotGate
          return json(
            server.snapshotOverrides[id] ??
              server.snapshotPages.flat().find((s) => s.id === id) ??
              snapshot(id),
          )
        }
        if (segments[5] === 'runs') return json(page(server.runPages, query.get('cursor')))
        if (segments[5] === 'annotation-items') {
          if (segments.length === 6) {
            // The public contract allows q to be absent, but supplied search text must be nonempty.
            if (query.has('q') && query.get('q') === '')
              return json(
                { error: { code: 'validation_error', message: 'q is empty', details: {} } },
                422,
              )
            return json(page(server.peoplePages, query.get('cursor')))
          }
          const record = server.knownPeople.find(
            (p) => p.tei_id === segments[6] && p.snapshot_id === id,
          )
          return record ? json(record) : json({}, 404)
        }
        if (segments[5] === 'people') {
          const record = server.knownPeople.find(
            (p) => p.tei_id === segments[6] && p.snapshot_id === id,
          )
          return record
            ? json({
                id: record.person_record_id,
                dataset_snapshot_id: id,
                tei_id: record.tei_id,
                surname: record.surname,
                forenames: record.forenames,
                alt_names: [],
                occupations: [],
                events: [],
                external_ids: {},
                metadata: {},
                source_document_id: null,
                created_at: '2026-01-02T10:00:00Z',
              })
            : json({}, 404)
        }
      }
      if (segments[3] === 'runs') {
        const id = segments[4] ?? ''
        if (segments[5] === 'aggregations')
          return json(page(server.resultPages, query.get('cursor')))
        if (segments[5] === 'executions') return json([])
        return json(
          server.runOverrides[id] ?? server.runPages.flat().find((r) => r.id === id) ?? run(id),
        )
      }
      if (segments[3] === 'aggregations' && segments.length === 5)
        return json(
          server.resultPages.flat().find((r) => r.id === segments[4]) ?? result(segments[4]),
        )
      if (path === '/api/v1/annotations') {
        if (request.method === 'POST') {
          const body = (await request.json()) as components['schemas']['AnnotationCreate']
          server.posts.push(body)
          const annotation = {
            ...body,
            id: `annotation-${server.posts.length}`,
            person_record_id: `person-${body.tei_id}`,
            resulting_revision: body.expected_revision + 1,
            reviewer_user_id: 'user-1',
            reviewer_display_name: 'Editor',
            created_at: '2026-01-05T10:00:00Z',
            supersedes_annotation_id: null,
            aggregated_result_id: null,
          } as components['schemas']['AttributedAnnotation']
          const historyKey = `${body.snapshot_id}:${body.tei_id}`
          server.histories[historyKey] = {
            snapshot_id: body.snapshot_id,
            tei_id: body.tei_id,
            person_record_id: `person-${body.tei_id}`,
            revision: annotation.resulting_revision,
            workflow_state: 'reviewed',
            current_annotation_id: annotation.id,
            annotations: [annotation],
          }
          for (const entry of [...server.knownPeople, ...server.peoplePages.flat()]) {
            if (entry.snapshot_id === body.snapshot_id && entry.tei_id === body.tei_id) {
              entry.human_label = body.label ?? null
              entry.review_revision = annotation.resulting_revision
              entry.workflow_state = 'reviewed'
              entry.current_annotation_id = annotation.id
            }
          }
          return json(annotation, 201)
        }
        const snapshotId = query.get('snapshot_id') ?? SNAPSHOT
        const tei = query.get('tei_id') ?? 'demo-1'
        return json(
          server.histories[`${snapshotId}:${tei}`] ?? {
            snapshot_id: snapshotId,
            tei_id: tei,
            person_record_id: `person-${tei}`,
            revision: 0,
            workflow_state: 'unreviewed',
            current_annotation_id: null,
            annotations: [],
          },
        )
      }
      return json({}, 404)
    },
  })
}
