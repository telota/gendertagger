# ADR-0033: Project-scoped membership roles

**Status:** Accepted

## Context

[`13-auth-and-security.md`](../13-auth-and-security.md) defined four global, hierarchical roles —
`viewer` < `reviewer` < `operator` < `admin` — and recorded project-scoped permissions as future work in
[`22-future-development.md`](../22-future-development.md). Every project-scoped endpoint checked only the
global role, so any viewer could read every project, snapshot, run, aggregation, evaluation, and export by
identifier.

The accepted wireframe states that team membership is per project, and the frontend delivery plan records
the resulting conflict as decision D6 ([`24-frontend-delivery-plan.md`](../24-frontend-delivery-plan.md)).
D6 blocks `GET /projects`: the project list cannot be specified without deciding which projects a caller
sees, and narrowing it afterwards would change what existing clients can reach.

Scoping only the list would not have been enough. The item endpoints already exposed every project to every
viewer, so real scoping means resolving a caller's role against the project that owns each requested
resource, on every project-scoped endpoint.

Every project-scoped resource has exactly one owning project, reached through a single foreign-key path:
a snapshot through `dataset_snapshots.project_id`; a run through its snapshot; an aggregation, evaluation,
and export through their run. The create commands that name more than one resource already reject
identifiers from a different run or snapshot (`aggregation must belong to the export run`, `every selected
method execution must belong to the evaluation run`, `referenced aggregated result belongs to a different
person`), so authorizing the root identifier of a request authorizes the whole request.

## Decision

**Project roles.** A new `ProjectRole` has three hierarchical values, `viewer` < `reviewer` < `operator`, with
the capabilities the former global roles of the same names had, now limited to one project:

- `viewer`: read the project and everything it owns;
- `reviewer`: viewer, plus append annotations;
- `operator`: reviewer, plus import snapshots and create runs, aggregations, evaluations, and exports.

A user holds at most one role per project, recorded in a new `project_memberships` table with the primary
key `(project_id, user_id)`, a `role` check constraint, and `created_at`/`updated_at` timestamps.

**Global roles.** `Role` is renamed `GlobalRole` and narrowed to two values:

- `admin`: every project, with operator capability in each, plus membership administration;
- `operator`: may create projects. It grants no access to any existing project.

Global `viewer` and `reviewer` no longer exist. `CurrentUser.roles` carries only global roles.

**Effective role.** A caller's effective role in a project is `operator` for a global `admin`, otherwise the
caller's membership role in that project, otherwise none.

**Project creation.** `POST /projects` requires global `operator` or `admin`. The creating user becomes a
member with project role `operator` in the same transaction.

**Enforcement.** Each project-scoped route resolves the owning project of its root identifier — the path
parameter, or `dataset_snapshot_id`, `run_id`, `snapshot_id`, or `aggregation_id` where the identifier is in
the body or query — and compares the caller's effective role with the route's least project role. The root
identifier and least role of every route are listed in [`05-api.md`](../05-api.md).

- A resource that does not exist, or whose project the caller has no role in, returns
  `404 resource_not_found`. The response does not reveal whether a resource exists in another project.
- A caller with a role in the project that is below the route's least role receives `403 forbidden`.

`GET /methods` and `POST /classify` read no project data. They require at least one grant: any global role or
any project membership.

**Project list.** `GET /projects` returns a cursor-paginated `CursorPage[AccessibleProject]` of the projects
where the caller has an effective role, ordered by `slug` with the project ID as tie-breaker. An
`AccessibleProject` is a `Project` plus `current_user_role`, the caller's effective `ProjectRole`.
`POST /projects` and `GET /projects/{project_id}` return the same representation, so a client can scope its
controls to the current project without a second request.

**Membership administration.** Memberships are managed in two ways, both restricted to administrators:

- Admin-only HTTP endpoints: `GET /projects/{project_id}/members` returns the members as a list of
  `ProjectMember` sorted by display name; `PUT /projects/{project_id}/members/{user_id}` with a
  `ProjectMemberUpdate` grants or changes a role; `DELETE /projects/{project_id}/members/{user_id}`
  revokes it. Unknown projects, users, or memberships return `404`.
- CLI commands against the database: `gendertagger projects add-member`, `remove-member`, and
  `list-members`, addressing projects by slug and users by local-account username.

The service logs every grant, change, and revocation with the project, the member, the role, and the acting
administrator where one exists.

**Migration.** Revision `20260921_0004` creates `project_memberships`, deletes every global `viewer` and
`reviewer` row from `user_roles`, and narrows the `user_roles.role` check constraint to `operator` and
`admin`. It creates no memberships. After the upgrade, existing projects are visible only to administrators
until an administrator assigns members. Downgrade drops the table and restores the four-value constraint,
but cannot restore the deleted role rows.

## Consequences

- D6 is resolved. `GET /projects` is specified and implemented against its final visibility rule, so there is
  no provisional contract to narrow later.
- Projects are isolated from each other: a user sees only the registers of the teams they belong to, and an
  identifier leaked from another project behaves like one that does not exist.
- The upgrade is disruptive by design. Every non-admin user loses access until an administrator assigns
  project memberships, and former global operators keep only the right to create projects. Deployments must
  plan membership assignment as part of the upgrade.
- `CurrentUser.roles` and the `Role` schema change incompatibly: the schema is renamed `GlobalRole` and loses
  two values. The frontend used neither beyond generated types, so the OpenAPI snapshot and generated client
  are regenerated in the same change.
- Every project-scoped request performs an ownership lookup of at most three joins before its handler runs.
- A global operator who creates a project becomes its operator; removing that membership removes their
  access, because the global role does not grant it.
- Rejected: an additive model in which the effective role is the higher of a global role and a membership.
  It kept existing deployments working without data changes, but a single global role would have silently
  exposed every project, which defeats team isolation.
- Rejected: returning `403` for projects the caller cannot see. It would confirm that a resource exists in a
  project the caller does not belong to.
- Follow-up: the admin membership endpoints address users by ID, and no endpoint lists users yet, so an
  administrator screen would need a user directory. Membership changes are logged rather than kept as an
  append-only history; a durable audit trail for user and role changes remains in
  [`22-future-development.md`](../22-future-development.md).
