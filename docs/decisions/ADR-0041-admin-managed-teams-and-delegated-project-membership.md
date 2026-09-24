# ADR-0041: Admin-managed teams and delegated project membership

**Status:** Accepted

## Context

[ADR-0033](ADR-0033-project-scoped-membership-roles.md) establishes project-scoped `viewer`,
`reviewer`, and `operator` memberships, global `operator` and `admin` roles, project isolation,
and global-administrator-only project-membership administration. It does not define a collaborator
eligibility group or a transferable project-management authority.

[ADR-0039](ADR-0039-administer-local-accounts-over-http.md) provides a global-administrator-only
local-account directory. Its usernames, global roles, activation state, and password-security state
are administrative data; they must not become a directory for project managers.

The accepted design requires direct, administrator-managed teams. Team membership establishes who is
eligible for an explicit project grant; it must not itself expose a project. Every project belongs to
one team and has one transferable manager whose membership-administration authority is independent of
its ordinary project role.

There is no production database and no legacy projects, teams, or users to migrate. The repository's
pre-deployment migration policy therefore permits the baseline schema to be amended. No historical
creator, manager, team assignment, or temporary unassigned-project state is required or introduced.
This decision does not change scientific behavior.

## Decision

### Team, project, and role relationships

A user may directly belong to multiple teams. Teams have no hierarchy, invitation workflow, or
team-level role. A project belongs to exactly one team; cross-team projects and project transfers are
out of scope.

Team membership establishes eligibility only. It grants neither project visibility nor a project role.
`ProjectRole` remains unchanged:

- `viewer` reads the project and everything it owns;
- `reviewer` additionally appends annotations; and
- `operator` additionally imports snapshots and creates runs, aggregations, evaluations, and exports.

An assigned project has exactly one manager. Management is a distinct assignment, not a fourth
`ProjectRole` and not an implication of `operator`. A manager may hold any explicit project role,
including none. Transfer changes only manager authority; it never changes either party's ordinary
project membership.

A manager must be an active direct member of the project's team. An active direct team member is the
only non-administrator eligible target for a manager appointment or explicit project membership.

### Global roles and project creation

`GlobalRole.operator` remains the permission to create projects, not to access existing ones. An
operator may create a project only in a team of which the creator is an active direct member. In the
same transaction, the creator is recorded as historical creator, becomes the initial manager, and
receives ordinary project role `operator`.

`GlobalRole.admin` retains universal effective project role `operator` and team/account
administration without an explicit team or project membership. An administrator may create a project
for any team. If the administrator is not an active member of that team, the create command requires
an active direct team member as initial manager. The administrator is recorded as historical creator
but receives no ineligible explicit project membership.

Removing global `operator` does not remove existing project memberships or management assignments.
Removing global `admin` does not remove explicit project grants; the former administrator retains only
valid explicit project memberships and management assignments.

### Partial amendment to ADR-0033

This ADR amends only two ADR-0033 rules:

- Its project-creation rule now requires a team and records creator, manager, and eligible explicit
  membership as described above; and
- its global-admin-only membership-administration rule now permits an assigned project's manager to manage
  that project's eligible explicit memberships and manager transfer.

It does not amend ADR-0033's `ProjectRole` hierarchy, global-role vocabulary, effective-admin project role,
project-list visibility, ownership-path authorization, inaccessible-resource `404`, or insufficient-role
`403`. ADR-0033 remains accepted historical decision rather than superseded.

### Discovery, authority, and privacy

Global administrators administer accounts, teams, team membership, project-team assignment, and every
project's membership and manager. They continue to access every project without explicit membership.
`GET /admin/users` and all account-security/global-role metadata remain global-admin-only as decided
by ADR-0039.

A project manager may list that project's existing members, search active direct members of only that
project's team, grant or change their project roles, revoke their project roles, and transfer that
project's manager assignment. A manager cannot administer a team, access another project, or read the
global account directory.

Manager-facing candidate lookup is server-filtered, cursor-paginated, and stably ordered by normalized
display name and user ID. It returns only `id` and `display_name`. The server revalidates activity and
team eligibility in every manager write; client-side filtering is never an authorization boundary.

Ordinary project members and other team members may discover their own team summaries but cannot view
team rosters, enumerate candidates, or manage project memberships. A global operator who is not also
a manager has the same restrictions.

Every accessible-project response explicitly includes `current_user_can_manage_members`. It is true
for the current manager or a global administrator, never inferred from `current_user_role`.

### Persistence and canonical contracts

Pydantic models define the canonical request and response contracts. SQLAlchemy rows remain
persistence-only, and FastAPI remains the public interface. CLI commands invoke the same application
services directly rather than calling FastAPI or bypassing eligibility rules.

The conceptual schema adds:

- `teams`: UUID identity, unique normalized slug, display name, and timestamps;
- `team_memberships`: primary key `(team_id, user_id)` and creation timestamp;
- `projects.team_id`: non-null foreign key to `teams`;
- `projects.manager_user_id`: non-null manager identity constrained to the project team membership;
  and
- `projects.created_by_user_id`: non-null historical creator identity, never an authorization source.

`project_memberships` retains its existing `(project_id, user_id)` primary key and role constraint.
Every explicit project membership must be eligible through active direct team membership. The project
manager constraint uses the `(team_id, user_id)` team-membership key where PostgreSQL can enforce it;
activity and project-membership eligibility are revalidated by the application service inside the
mutation transaction.

The target public contracts include `TeamCreate`, `TeamUpdate`, `TeamSummary`, `TeamMember`,
`ProjectEligibleUser`, `ProjectManagerUpdate`, and the extended `ProjectCreate`, `ProjectMember`, and
`AccessibleProject` contracts. `ProjectCreate` adds required `team_id` and optional
`initial_manager_user_id`; omission selects the creator only when eligible. `ProjectMember` adds
`is_manager` and `AccessibleProject` adds a team summary plus
`current_user_can_manage_members`.

### HTTP, CLI, errors, and logging

The following target endpoints are relative to `/api/v1` and remain pending implementation:

| Endpoint | Authorization | Behavior |
| --- | --- | --- |
| `GET /teams` | Authenticated caller | Cursor-paginated summaries of the caller's teams; administrators see all teams. |
| `GET, POST /admin/teams` | Global admin | List teams or create one. |
| `PATCH, DELETE /admin/teams/{team_id}` | Global admin | Rename a team; delete only an empty team. |
| `GET /admin/teams/{team_id}/members` | Global admin | Read one team roster. |
| `POST /admin/teams/{team_id}/members` | Global admin | Add an active account by user ID. |
| `DELETE /admin/teams/{team_id}/members/{user_id}` | Global admin | Remove team membership and derived project grants. |
| `GET /projects/{project_id}/members` | Global admin or project manager | List explicit project memberships and manager state. |
| `GET /projects/{project_id}/eligible-users` | Global admin or project manager | Search minimal eligible-team-member candidates. |
| `PUT, DELETE /projects/{project_id}/members/{user_id}` | Global admin or project manager | Grant/change or revoke one eligible explicit project role. |
| `PUT /projects/{project_id}/manager` | Global admin or current manager | Transfer manager using `ProjectManagerUpdate`. |

An administrator-only project-team assignment command is unnecessary because the first deployed schema
contains no legacy projects. The CLI retains administrative break-glass commands and gains matching
team, manager, and team-aware project-membership commands through application services.

A manager requesting an inaccessible project, or targeting an unknown, inactive, or ineligible user,
receives `404 resource_not_found`. This does not disclose account-directory information. A member
below the necessary project role retains `403 forbidden`. A manager departure/deactivation without a
replacement returns `409 manager_replacement_required`; a stale manager transfer returns
`409 project_manager_conflict`; and a write that loses a race to team-member removal returns
`409 team_membership_conflict`. Invalid commands retain `422 validation_error`.

All authenticated routes retain the existing authentication, password-current, and unsafe-request CSRF
protections. Successful team, manager, and project-membership mutations log actor ID or `cli`, request
ID where available, action, affected IDs, and non-secret changed fields. No audit-history table is
introduced, and logs exclude passwords, password hashes, sessions, CSRF tokens, and complete
secret-bearing bodies.

### Lifecycle, atomicity, and concurrency

Removing a team member atomically removes that member's explicit project memberships in every project
assigned to that team. It does not delete the account, historical creator attribution, annotation
history, or scientific work. Rejoining creates only a new team membership and never restores prior
project roles or manager assignments.

An inactive account cannot be added to a team. Deactivation revokes sessions and, after any required
manager replacements, removes the account's team memberships and resulting project grants in the same
transaction. Reactivation restores neither sessions nor removed access.

A team member who manages one or more projects cannot be removed or deactivated until every affected
project has an explicitly appointed active eligible replacement. No automatic successor, system
manager, or managerless-project state exists. A global administrator recovers by adding an active
account to the team, appointing it manager, then removing or deactivating the previous manager.

Every mutation whose validity depends on a team's membership acquires a transaction-scoped PostgreSQL
advisory lock namespaced by team ID. The transaction then locks and freshly revalidates the project,
target user, and relevant team-membership rows before commit. Team member removal locks affected
project rows in deterministic UUID order. This covers team removal, project creation, manager transfer,
and membership writes without a generic authorization framework.

`ProjectManagerUpdate` carries the expected current manager ID. A stale transfer conflicts rather than
silently replacing a newer transfer. Concurrent ordinary role writes are serialized; the later valid
committed write is authoritative and clients refresh membership state. No invalid grant may commit when
it races a team-member removal.

### Delivery and compatibility

Implementation proceeds in reviewed, manually committed slices:

1. **Team persistence and administrative APIs.** Add team contracts, baseline schema, repositories,
   services, admin-only endpoints, CLI commands, operational logs, generated contract updates, and
   focused tests. This slice does not change project creation, project visibility, or membership
   authorization.
2. **Project/team association, manager authority, and membership APIs.** Add required project team,
   manager, and creator relationships; team-aware creation; delegated membership endpoints; candidate
   discovery; concurrency protection; CLI parity; and focused tests. An old project-create client fails
   validation once this contract lands; it cannot create an unassigned project or bypass eligibility.
3. **Team administration UI.** Add administrator team and roster flows with principal-scoped private
   caches, access-loss cleanup, localization, and accessibility verification.
4. **Project creation integration and project-membership UI.** Regenerate transport types, add creator
   team selection, administrator initial-manager selection, manager membership management, candidate
   search, transfer handling, cache invalidation, and browser verification.

Every slice stops for review and a manual commit. The first slice is safe in isolation because it does
not change the existing project authorization path. The second slice changes the project-create contract
and must be coordinated with generated frontend transport types; the old client fails closed rather than
creating an unscoped project. The later UI slices consume only completed backend contracts.

Future verification covers role and privacy boundaries, scoped candidate discovery, team-removal/grant
races, manager departure and administrator recovery, deactivation/rejoin non-restoration, fresh-schema
creation, legacy-client fail-closed behavior, CLI parity, stale principal-scoped frontend caches, and
existing account/project behavior. Required documentation, contract, type, lint, migration, backend,
frontend, and browser checks are run in their applicable implementation slices, not by this decision.

## Consequences

- ADR-0033's project roles, effective-admin access, project-resource `404` hiding, and lower-role `403`
  behavior remain accepted.
- This ADR partially amends ADR-0033's project-creation and membership-administration rules: eligible
  project managers may administer only their own assigned project's memberships, while global
  administrators retain authority everywhere.
- ADR-0039 remains unchanged: only global administrators receive account-directory and account-security
  data. Managers receive a separate minimal, scoped candidate projection.
- The absence of production and legacy data enables a clean schema cutover: no permissive default team,
  inferred owner, historical backfill, or temporary unassigned-project compatibility path is introduced.
- Team membership is not automatic project access; no team-wide grant, organizational hierarchy,
  invitation workflow, SSO integration, cross-team project, project transfer, generic policy engine,
  audit-history system, or scientific change is added.
- Requiring explicit manager replacement makes departures operationally deliberate but preserves a
  simple one-manager invariant and prevents abandoned delegated authority.
