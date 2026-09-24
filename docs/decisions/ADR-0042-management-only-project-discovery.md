# ADR-0042: Management-only project discovery

**Status:** Accepted

## Context

[ADR-0041](ADR-0041-admin-managed-teams-and-delegated-project-membership.md) permits an assigned
project manager to administer that project's memberships independently of an ordinary `ProjectRole`.
The delivered management endpoints accept a `project_id`, but `GET /projects` intentionally lists only
projects the caller can read. A manager without an ordinary project membership therefore cannot discover
or reopen a management surface without either guessing an identifier or requesting project data that they
are not authorized to read.

The browser needs a durable, cursor-paginated management entry point while preserving ADR-0033's
project-data privacy and ordinary project-list visibility.

## Decision

Add authenticated `GET /api/v1/projects/managed`. It returns a cursor-paginated, slug-ordered collection
of `ManagedProjectSummary` records for projects whose current `manager_user_id` equals the caller's ID.
The collection is a management-only discovery resource, not an accessible-project collection. It does not
change `GET /projects` or grant a project role.

`ManagedProjectSummary` contains only the project's UUID, slug, display name, and roster-free
`TeamSummary`. It omits description, creator, working aggregation, snapshots, runs, annotations,
evaluations, exports, and every other scientific project-data field. It carries no inferred project role.

A global administrator continues to discover every project through `GET /projects`, where the existing
contract already grants effective administrator access and `current_user_can_manage_members`. The new
collection is for a caller's explicit manager assignments only.

The management UI may use a `ManagedProjectSummary` to enter its membership surface, then call the
existing management-authorized roster, eligible-user, role-mutation, and manager-transfer endpoints. It
must not request `GET /projects/{project_id}` merely to render management context for a manager without
an ordinary project role.

## Consequences

- Managers without a project role can discover only projects they currently manage and can manage no
  scientific project data through this route.
- An ordinary global operator without a manager assignment receives an empty collection.
- A successful manager transfer removes the former manager from this collection and exposes the new
  manager on their next read; the UI must refresh rather than infer continuity.
- The route, Pydantic model, OpenAPI snapshot, generated frontend transport types, authorization tests,
  and development seed scenarios evolve together as a public contract.
- This decision adds one narrowly scoped discovery resource rather than broadening `GET /projects` or
  weakening project-resource `404` behavior.
