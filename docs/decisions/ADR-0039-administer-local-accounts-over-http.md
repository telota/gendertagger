# ADR-0039: Administer local accounts over HTTP

**Status:** Accepted

## Context

[ADR-0031](ADR-0031-local-database-authentication.md) made local-account provisioning and administrative
password reset CLI-only because the first frontend scope contained no user-management screen. The browser
client now needs a global-administrator area for account discovery, creation, updates, and password resets.
Project-membership administration already has admin-only HTTP resources, but those resources are impractical
without a user directory that resolves usernames and display names to user IDs.

The existing `AuthenticationService` already creates local accounts, resets passwords, and revokes sessions.
The provider-neutral `User` contract already represents activation and global roles, but its repository has no
collection query or update operations. Extending these application boundaries is preferable to making the
browser invoke the CLI or exposing persistence models.

A durable, queryable administrative audit trail would add a new event model, persistence, API, retention
policy, and frontend surface. That cost is not justified for this increment. Successful administrative changes
still need operational attribution, while credentials and session secrets must never enter logs.

## Decision

Add a global-admin-only HTTP surface for local-account administration. FastAPI remains the public boundary,
Pydantic models define every request and response, and route handlers call application services directly.
SQLAlchemy rows and password hashes never cross the service or API boundaries.

The surface supports:

- a server-filtered, opaque-cursor-paginated user directory searchable by normalized username or display name;
- local-account creation with display name, normalized username, and global roles;
- display-name, activation-state, and global-role updates; and
- local-account password reset.

Account creation returns a server-generated temporary password once. The response is marked non-cacheable,
and the password is never persisted in plaintext or included in application logs. The existing CLI commands
remain available as a break-glass path and use the same application service.

Password reset accepts no body. It validates the local target inside its mutation transaction, replaces the
credential hash, flags `must_change_password`, and revokes every existing target session in that transaction.
It never reactivates an inactive target. Each successful reset returns a fresh server-generated temporary
password once in a non-cacheable response. The HTTP command requires a global administrator and follows the
standard CSRF and password-current gates.

Accounts are deactivated, never deleted. This preserves foreign-key references and scholarly attribution.
Deactivation revokes every active session in the same transaction. Reactivation does not restore revoked
sessions. Session revocation is a no-op when no active session remains, and activation or role updates are
idempotent where the requested state already holds.

The application service enforces these invariants in addition to the route-level `admin` dependency:

- an administrator cannot deactivate their own account or remove their own `admin` role;
- at least one active administrator must remain; and
- every account, role, and credential mutation validates the target inside the transaction that persists it.

For every local-account patch, the service first acquires a fixed transaction-level PostgreSQL advisory lock.
After acquiring that serialization lock, it runs a fresh active-administrator query and revalidates the actor
before locking the target user and applying a mutation. The fresh query is necessary because a joined
`SELECT ... FOR UPDATE` that waited on a `users` row cannot be relied upon to refresh the associated
`user_roles` membership. The advisory lock serializes the complete administrative update and releases at
transaction end. The session revocation update and account update share that same transaction.

Successful mutations emit structured operational logs containing the acting user ID, action, target user ID,
request ID, and non-secret changed fields. Logs never contain passwords, password hashes, session or CSRF
tokens, API keys, or complete secret-bearing request bodies. A persisted administrative event history and an
audit-log UI remain deferred.

Project-membership administration and application settings are outside this decision. They remain separate
increments so each public-contract change has a small review and rollback surface.

## Consequences

- The browser can administer local accounts without access to the host or database.
- Authorization remains server-side and deny-by-default; hiding frontend controls is not the security boundary.
- User collection queries must use server-side filtering and cursor pagination rather than loading every user.
- Deactivation terminates existing sessions without deleting their rows.
- The user repository and authentication service gain update and collection operations, but their existing CLI
  consumers remain valid.
- ADR-0031's CLI-only provisioning and password-reset decisions are superseded; its authentication,
  credential, session, cookie, and forced-password-change decisions remain accepted.
- Operational logs provide lightweight attribution but are not a tamper-resistant or application-queryable
  audit history. Deployments that require such a history need a later explicit decision.
- Self-service registration, email recovery, user deletion, project memberships, application settings, and
  external identity-provider administration remain out of scope.
