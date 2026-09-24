import { createApiClient } from '@/api'

import {
  AGG_ID,
  jsonResponse,
  newServer,
  PROJECT_ID,
  reviewFetch,
  RUN_ID,
  SNAPSHOT_ID,
  type Server,
} from '../features/review/fixtures'
import realReport from '../features/evaluation/fixtures/seed-report.json'

/**
 * One in-memory API that can serve every screen with realistic data, for checks that walk the whole
 * application (accessibility). The review endpoints come from the review fixture; everything else the
 * other screens read is answered here, in the shapes the real API returns.
 */
export const EVALUATION_ID = 'e1000000-0000-0000-0000-000000000001'
export const EXPORT_ID = 'e2000000-0000-0000-0000-000000000001'
export const RUNNING_RUN_ID = 'd0000000-0000-0000-0000-0000000000ff'

const EXECUTIONS = [
  ['x0000000-0000-0000-0000-000000000001', 'parenthetical_qualifier', 'completed'],
  ['x0000000-0000-0000-0000-000000000002', 'gnd', 'completed'],
  ['x0000000-0000-0000-0000-000000000003', 'gender_guesser', 'completed_with_errors'],
  ['x0000000-0000-0000-0000-000000000004', 'local_llm', 'failed'],
] as const

const progress = { completed: 7, failed: 1, total: 8, percentage: 100 }

function run(id: string, status: string) {
  return {
    id,
    dataset_snapshot_id: SNAPSHOT_ID,
    status,
    created_at: '2026-01-01T10:00:00Z',
    started_at: '2026-01-01T10:00:01Z',
    finished_at: status === 'running' ? null : '2026-01-01T10:01:00Z',
    config_sha256: 'e'.repeat(64),
    resolved_config: {
      methods: EXECUTIONS.map(([, name]) => ({ name, enabled: true, config: {} })),
      aggregation: { strategy: 'reference_v1' },
      execution: { fail_run_on_optional_method_error: false },
    },
    progress:
      status === 'running' ? { completed: 3, failed: 0, total: 8, percentage: 37.5 } : progress,
    application_version: '0.1.0',
    code_git_commit: 'c'.repeat(40),
    python_version: '3.12.4',
    container_image_digest: null,
    dependency_lock_sha256: 'd'.repeat(64),
    failure_class: null,
    failure_diagnostic: null,
  }
}

function execution([id, name, status]: (typeof EXECUTIONS)[number]) {
  return {
    id,
    run_id: RUN_ID,
    method_name: name,
    status,
    progress: { completed: 3, failed: status === 'completed' ? 0 : 1, total: 4, percentage: 100 },
    completed_count: 3,
    failed_count: status === 'completed' ? 0 : 1,
    total_count: 4,
    implementation_version: `${name}_v1`,
    normalization_version: `${name}_v1`,
    config_sha256: 'f'.repeat(64),
    resolved_config: {},
    model_identifier: name === 'local_llm' ? 'llama3' : null,
    model_revision: name === 'local_llm' ? 'rev-7' : null,
    prompt_version: name === 'local_llm' ? 'prompt_v2' : null,
    failure_class: status === 'failed' ? 'ModelUnavailable' : null,
    failure_diagnostic: status === 'failed' ? 'the model server did not answer' : null,
    created_at: '2026-01-01T10:00:00Z',
  }
}

const AGGREGATION = {
  id: AGG_ID,
  run_id: RUN_ID,
  strategy: 'reference_v1',
  status: 'completed',
  resolved_config: {},
  method_execution_ids: EXECUTIONS.map(([id]) => id),
  config_sha256: '9'.repeat(64),
  created_at: '2026-01-01T11:00:00Z',
  started_at: '2026-01-01T11:00:01Z',
  finished_at: '2026-01-01T11:00:05Z',
}

const EVALUATION = {
  id: EVALUATION_ID,
  run_id: RUN_ID,
  definition: 'gnd_benchmark_v1',
  aggregation_execution_id: AGG_ID,
  config_sha256: '8'.repeat(64),
  resolved_config: { id: 'gnd_benchmark_v1', confidence_level: 0.95 },
  method_execution_ids: EXECUTIONS.map(([id]) => id),
  status: 'completed',
  report_artifact_id: 'artifact',
  created_at: '2026-01-01T12:00:00Z',
  started_at: '2026-01-01T12:00:01Z',
  finished_at: '2026-01-01T12:00:05Z',
  failure_class: null,
  failure_diagnostic: null,
}

const EXPORT = {
  id: EXPORT_ID,
  run_id: RUN_ID,
  aggregation_execution_id: AGG_ID,
  format: 'tei',
  label_source_policy: 'human_overrides',
  tei_profile: 'tei_p5_gender_v1',
  human_resp_id: '#editor',
  status: 'completed',
  manifest_artifact_id: 'artifact',
  created_at: '2026-01-01T13:00:00Z',
  started_at: '2026-01-01T13:00:01Z',
  finished_at: '2026-01-01T13:00:05Z',
  failure_class: null,
  failure_diagnostic: null,
}

const page = (items: unknown[]) => ({ items, next_cursor: null, has_more: false })

/** A `fetch` for the whole application. `server` steers the review endpoints (role, people, writes). */
export function applicationFetch(server: Server): (request: Request) => Promise<Response> {
  const review = reviewFetch(server)
  return async (request) => {
    const { pathname } = new URL(request.url)
    if (pathname === '/api/v1/projects') {
      return jsonResponse(
        page([
          {
            id: PROJECT_ID,
            slug: 'demo',
            display_name: 'Project A',
            description: 'A demonstration project.',
            current_user_role: server.role,
            created_at: '2026-01-01T00:00:00Z',
            working_aggregation_execution_id: AGG_ID,
          },
        ]),
      )
    }
    if (pathname === `/api/v1/projects/${PROJECT_ID}/snapshots`) {
      return jsonResponse(
        page([
          {
            id: SNAPSHOT_ID,
            project_id: PROJECT_ID,
            source_artifact_id: 'a',
            source_sha256: 'a'.repeat(64),
            parser_version: 'tei_parser_v3',
            status: 'ready',
            record_count: 7,
            created_at: '2026-01-01T00:00:00Z',
            ready_at: '2026-01-01T00:00:05Z',
            import_config: { source_format: 'tei', packaging: 'single' },
          },
          {
            id: 'c0000000-0000-0000-0000-0000000000ee',
            project_id: PROJECT_ID,
            source_artifact_id: 'b',
            source_sha256: 'b'.repeat(64),
            parser_version: 'tabular_person_parser_v1',
            status: 'failed',
            failure_class: 'TabularImportError',
            failure_diagnostic: 'Tabular import failed: CSV header contains unknown columns',
            created_at: '2026-01-02T00:00:00Z',
            import_config: { source_format: 'csv', packaging: 'single' },
          },
        ]),
      )
    }
    if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}/source-members`) {
      return jsonResponse([
        {
          artifact_id: 'a',
          byte_size: 1024,
          created_at: '2026-01-01T00:00:00Z',
          dataset_snapshot_id: SNAPSHOT_ID,
          id: 'm1',
          logical_name: 'persons-a.xml',
          media_type: 'application/tei+xml',
          ordinal: 0,
          sha256: 'a'.repeat(64),
        },
      ])
    }
    if (pathname === '/api/v1/snapshot-upload-limits') {
      return jsonResponse({
        max_upload_part_bytes: 104857600,
        max_total_upload_bytes: 524288000,
        import_limits: { max_member_count: 128, max_total_expanded_bytes: 524288000 },
      })
    }
    if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}`) {
      return jsonResponse({
        id: SNAPSHOT_ID,
        project_id: PROJECT_ID,
        source_artifact_id: 'a',
        source_sha256: 'a'.repeat(64),
        parser_version: 'tei_parser_v3',
        status: 'ready',
        record_count: 7,
        created_at: '2026-01-01T00:00:00Z',
        import_config: { source_format: 'tei', packaging: 'single' },
      })
    }
    if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}/runs`) {
      return jsonResponse(
        page([run(RUN_ID, 'completed_with_errors'), run(RUNNING_RUN_ID, 'running')]),
      )
    }
    if (pathname === `/api/v1/runs/${RUN_ID}`)
      return jsonResponse(run(RUN_ID, 'completed_with_errors'))
    if (pathname === `/api/v1/runs/${RUNNING_RUN_ID}`)
      return jsonResponse(run(RUNNING_RUN_ID, 'running'))
    if (pathname === '/api/v1/methods') {
      return jsonResponse(
        EXECUTIONS.map(([, name]) => ({
          name,
          implementation_version: `${name}_v1`,
          normalization_version: `${name}_v1`,
          method_confidence_range: name === 'local_llm' ? { minimum: 0, maximum: 1 } : null,
        })),
      )
    }
    if (pathname === `/api/v1/runs/${RUN_ID}/executions`)
      return jsonResponse(EXECUTIONS.map(execution))
    if (pathname === `/api/v1/runs/${RUNNING_RUN_ID}/executions`) {
      return jsonResponse(EXECUTIONS.map(execution))
    }
    if (pathname === `/api/v1/runs/${RUN_ID}/aggregations`) return jsonResponse(page([AGGREGATION]))
    if (pathname === `/api/v1/aggregations/${AGG_ID}`) return jsonResponse(AGGREGATION)
    if (pathname === `/api/v1/runs/${RUN_ID}/evaluations`) return jsonResponse(page([EVALUATION]))
    if (pathname === `/api/v1/evaluations/${EVALUATION_ID}`) return jsonResponse(EVALUATION)
    if (pathname === `/api/v1/evaluations/${EVALUATION_ID}/report`) return jsonResponse(realReport)
    if (pathname === `/api/v1/runs/${RUN_ID}/exports`) return jsonResponse(page([EXPORT]))
    if (pathname === `/api/v1/exports/${EXPORT_ID}`) return jsonResponse(EXPORT)
    return review(request)
  }
}

export function applicationClient(server: Server = newServer({ role: 'operator' })) {
  return createApiClient({ fetch: applicationFetch(server) })
}

export const SCREENS = {
  projects: '/projects',
  overview: `/projects/${PROJECT_ID}/overview`,
  import: `/projects/${PROJECT_ID}/import`,
  runs: `/projects/${PROJECT_ID}/snapshots/${SNAPSHOT_ID}/runs`,
  run: `/projects/${PROJECT_ID}/snapshots/${SNAPSHOT_ID}/runs/${RUN_ID}`,
  aggregation: `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}`,
  review: `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/review`,
  people: `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/people`,
  evaluations: `/projects/${PROJECT_ID}/runs/${RUN_ID}/evaluations`,
  evaluation: `/projects/${PROJECT_ID}/runs/${RUN_ID}/evaluations/${EVALUATION_ID}`,
  exports: `/projects/${PROJECT_ID}/runs/${RUN_ID}/exports`,
  export: `/projects/${PROJECT_ID}/runs/${RUN_ID}/exports/${EXPORT_ID}`,
} as const
