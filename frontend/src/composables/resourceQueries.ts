import type { QueryClient } from '@tanstack/vue-query'

import type { paths } from '@/api'

type PrincipalId = string | null | undefined

/** Resource prefixes are stable; principal ownership is appended for private resource projections. */
export function privateQueryKey<T extends readonly unknown[]>(
  resourceKey: T,
  principalId: PrincipalId,
) {
  return [...resourceKey, { principal_id: principalId ?? null }] as const
}

export function belongsToPrincipal(
  queryKey: readonly unknown[],
  principalId: string | null,
): boolean {
  const owner = queryKey.at(-1)
  return (
    typeof owner === 'object' &&
    owner !== null &&
    'principal_id' in owner &&
    owner.principal_id === principalId
  )
}

export const PROJECTS_QUERY_KEY = ['projects'] as const
const ADMIN_TEAMS_QUERY_ROOT = ['admin', 'teams'] as const
const ADMIN_TEAM_ROSTER_QUERY_ROOT = ['admin', 'team-members'] as const
const ADMIN_USERS_QUERY_ROOT = ['admin', 'users'] as const

export function adminTeamsQueryKey(principalId: string, search: string) {
  return [...ADMIN_TEAMS_QUERY_ROOT, principalId, search] as const
}
export function adminTeamRosterQueryKey(principalId: string, teamId: string, search: string) {
  return [...ADMIN_TEAM_ROSTER_QUERY_ROOT, principalId, teamId, search] as const
}
export function adminUsersQueryKey(principalId: string, search: string) {
  return [...ADMIN_USERS_QUERY_ROOT, principalId, search] as const
}

/** Cancelling and removing every search variant prevents obsolete administrator reads resurfacing. */
export function clearAdminTeamQueries(queryClient: QueryClient, principalId: string): void {
  const teamQueryKey = [...ADMIN_TEAMS_QUERY_ROOT, principalId] as const
  const rosterQueryKey = [...ADMIN_TEAM_ROSTER_QUERY_ROOT, principalId] as const
  void queryClient.cancelQueries({ queryKey: teamQueryKey })
  void queryClient.cancelQueries({ queryKey: rosterQueryKey })
  queryClient.removeQueries({ queryKey: teamQueryKey })
  queryClient.removeQueries({ queryKey: rosterQueryKey })
}

export function clearAdminUserQueries(queryClient: QueryClient, principalId: string): void {
  const queryKey = [...ADMIN_USERS_QUERY_ROOT, principalId] as const
  void queryClient.cancelQueries({ queryKey })
  queryClient.removeQueries({ queryKey })
}

export function invalidateAdminTeamQueries(
  queryClient: QueryClient,
  principalId: string,
  throwOnError = false,
): Promise<void> {
  return Promise.all([
    queryClient.invalidateQueries(
      { queryKey: [...ADMIN_TEAMS_QUERY_ROOT, principalId] },
      { throwOnError },
    ),
    queryClient.invalidateQueries(
      { queryKey: [...ADMIN_TEAM_ROSTER_QUERY_ROOT, principalId] },
      { throwOnError },
    ),
    queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY }, { throwOnError }),
  ]).then(() => undefined)
}
/** Security writes can reject a follow-up refetch without retaining private mutation results. */
export function invalidateAdminUserQueries(
  queryClient: QueryClient,
  principalId: string,
  throwOnError = false,
): Promise<void> {
  return queryClient.invalidateQueries(
    { queryKey: [...ADMIN_USERS_QUERY_ROOT, principalId] },
    { throwOnError },
  )
}

export function projectListKey(principalId: PrincipalId, pageSize?: number) {
  return pageSize === undefined
    ? (['projects', 'list', principalId ?? 'anonymous'] as const)
    : (['projects', 'list', 'preview', pageSize, principalId ?? 'anonymous'] as const)
}
export function projectKey(projectId: string, principalId: PrincipalId) {
  return ['projects', projectId, principalId ?? 'anonymous'] as const
}
export function managedProjectsKey(principalId: PrincipalId) {
  return ['managed-projects', principalId ?? 'anonymous'] as const
}
export function projectCreationTeamsKey(principalId: PrincipalId, search: string) {
  return ['project-creation', 'teams', principalId ?? 'anonymous', search] as const
}
export function projectCreationRosterKey(principalId: PrincipalId, teamId: string | null) {
  return ['project-creation', 'team-roster', principalId ?? 'anonymous', teamId ?? 'none'] as const
}
export function projectMembershipQueryKey(principalId: PrincipalId, projectId: string) {
  return ['project-members', principalId ?? 'anonymous', projectId] as const
}
export function projectEligibleUsersKey(principalId: PrincipalId, projectId: string) {
  return ['project-eligible-users', principalId ?? 'anonymous', projectId] as const
}
export function snapshotListKey(projectId: string) {
  return ['projects', projectId, 'snapshots'] as const
}
export function snapshotListQueryKey(projectId: string, principalId: PrincipalId) {
  return [...snapshotListKey(projectId), principalId ?? 'anonymous'] as const
}
export function snapshotSourceMembersKey(snapshotId: string, principalId: PrincipalId) {
  return ['snapshots', snapshotId, 'source-members', principalId ?? 'anonymous'] as const
}
// Inspection and import-status have intentionally different eligibility and cache identities.
export function importedSnapshotKey(
  principalId: PrincipalId,
  projectId: string,
  snapshotId: string,
) {
  return ['imported-snapshot', principalId, projectId, snapshotId] as const
}
export function snapshotStatisticsKey(
  principalId: PrincipalId,
  projectId: string,
  snapshotId: string,
) {
  return ['snapshot-statistics', principalId, projectId, snapshotId] as const
}
export function importedPeopleKey(principalId: PrincipalId, projectId: string, snapshotId: string) {
  return ['imported-people', principalId, projectId, snapshotId] as const
}
export function importedPersonKey(
  principalId: PrincipalId,
  projectId: string,
  snapshotId: string,
  teiId: string | null,
) {
  return ['imported-person', principalId, projectId, snapshotId, teiId] as const
}
export function snapshotImportStatusKey(
  principalId: PrincipalId,
  projectId: string | null,
  snapshotId: string | null,
) {
  return ['snapshots', 'import-status', principalId ?? 'anonymous', projectId, snapshotId] as const
}
export function snapshotUploadLimitsKey() {
  return ['snapshot-upload-limits'] as const
}

export function runListKey(snapshotId: string) {
  return ['snapshots', snapshotId, 'runs'] as const
}
export function runKey(runId: string) {
  return ['runs', runId] as const
}
export function runExecutionsKey(runId: string) {
  return ['runs', runId, 'executions'] as const
}
export function aggregationListKey(runId: string) {
  return ['runs', runId, 'aggregations'] as const
}
export function aggregationKey<T extends string | null>(aggregationId: T) {
  return ['aggregations', aggregationId] as const
}
export function evaluationListKey(runId: string) {
  return ['runs', runId, 'evaluations'] as const
}
export function evaluationKey(evaluationId: string) {
  return ['evaluations', evaluationId] as const
}
export function evaluationReportKey(evaluationId: string) {
  return ['evaluations', evaluationId, 'report'] as const
}
export function exportListKey(runId: string) {
  return ['runs', runId, 'exports'] as const
}
export function exportKey(exportId: string) {
  return ['exports', exportId] as const
}
export function exportManifestKey(exportId: string) {
  return ['exports', exportId, 'manifest'] as const
}
export function methodExecutionResultsKey(
  principalId: PrincipalId,
  runId: string,
  executionId: string,
  search: string,
) {
  return [
    'method-execution-results',
    principalId ?? 'anonymous',
    runId,
    executionId,
    search,
  ] as const
}

export type ReviewItemsQuery = NonNullable<
  paths['/api/v1/review-items']['get']['parameters']['query']
>
export function reviewItemsResourceKey(aggregationId: string, query: ReviewItemsQuery) {
  return [...reviewItemsPrefix(aggregationId), query] as const
}
export function reviewItemsPrefix(aggregationId: string) {
  return ['aggregations', aggregationId, 'review-items'] as const
}
export function reviewItemPrefix(aggregationId: string) {
  return ['aggregations', aggregationId, 'review-item'] as const
}
export function reviewItemKey(aggregationId: string, teiId: string | null) {
  return [...reviewItemPrefix(aggregationId), teiId] as const
}
export function reviewSummaryKey(aggregationId: string) {
  return ['aggregations', aggregationId, 'review-summary'] as const
}
export function resultPredictionsKey(aggregationId: string, resultId: string | null) {
  return ['aggregations', aggregationId, 'results', resultId, 'predictions'] as const
}
export function annotationHistoryKey(snapshotId: string, teiId: string) {
  return ['snapshots', snapshotId, 'annotations', teiId] as const
}
export function personRecordKey(snapshotId: string | null, teiId: string | null) {
  return ['snapshots', snapshotId, 'people', teiId] as const
}
export function snapshotAnnotationItemsPrefix(snapshotId: string) {
  return ['snapshot-annotation-items', snapshotId] as const
}
export function snapshotAnnotationItemPrefix(snapshotId: string) {
  return ['snapshot-annotation-item', snapshotId] as const
}
type SnapshotAnnotationQuery = NonNullable<
  paths['/api/v1/snapshots/{snapshot_id}/annotation-items']['get']['parameters']['query']
>
export function snapshotAnnotationItemsKey(
  snapshotId: string,
  principalId: PrincipalId,
  query: SnapshotAnnotationQuery,
) {
  return [...snapshotAnnotationItemsPrefix(snapshotId), principalId, query] as const
}
export function snapshotAnnotationItemKey(
  snapshotId: string,
  principalId: PrincipalId,
  teiId: string,
) {
  return [...snapshotAnnotationItemPrefix(snapshotId), principalId, teiId] as const
}

export function projectDataAvailabilityKey(principalId: PrincipalId, projectId: string) {
  return ['project-data-availability', principalId, projectId] as const
}
export function taskSnapshotsKey(
  principalId: PrincipalId,
  projectId: string,
  resultsOnly: boolean,
) {
  return ['task-snapshots', principalId, projectId, resultsOnly] as const
}
export function taskRunsKey(principalId: PrincipalId, snapshotId: string) {
  return ['task-runs', principalId, snapshotId] as const
}
export function taskResultsKey(principalId: PrincipalId, runId: string) {
  return ['task-results', principalId, runId] as const
}
export function projectReviewResultsKey(principalId: PrincipalId, projectId: string) {
  return ['project-review-results', principalId, projectId] as const
}
// Task route projections validate a snapshot/project tuple; a bare run-detail read must not share it.
export function taskRunKey(
  principalId: PrincipalId,
  projectId: string,
  snapshotId: string,
  runId: string,
) {
  return ['task-run', principalId, projectId, snapshotId, runId] as const
}
export function workingSelectionKey(
  principalId: PrincipalId,
  projectId: string,
  aggregationId: string | null,
) {
  return ['working-selection', principalId, projectId, aggregationId] as const
}
