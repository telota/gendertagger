# ADR-0039: Administer local accounts over HTTP

**Status:** Accepted

## Context

[ADR-0031](ADR-0031-local-database-authentication.md) made local-account provisioning and administrative
password reset CLI-only because the first frontend scope contained no user-management screen. The browser
client now needs a global-administrator area for the complete local-account lifecycle. Project-membership
administration already has admin-only HTTP resources, but those resources are impractical without a user
directory that resolves usernames and display names to user IDs.

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
- display-name, activation-state, and global-role updates;
- administrative password reset, which flags a forced password change and revokes all existing sessions; and
- explicit revocation of all sessions for one user.

Administrative password reset returns a server-generated temporary password once. The response is marked
non-cacheable, and the password is never persisted in plaintext or included in application logs. Account
creation follows the same temporary-password behavior. The existing CLI commands remain available as a
break-glass path and use the same application service.

Accounts are deactivated, never deleted. This preserves foreign-key references and scholarly attribution.
Deactivation revokes every active session in the same transaction. Reactivation does not restore revoked
sessions. Session revocation is a no-op when no active session remains, and activation or role updates are
idempotent where the requested state already holds. Every password reset deliberately rotates the temporary
password.

The application service enforces these invariants in addition to the route-level `admin` dependency:

- an administrator cannot deactivate their own account or remove their own `admin` role;
- at least one active administrator must remain; and
- every account and role mutation validates the target inside the transaction that persists it.

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
- Deactivation, reset, and explicit revocation terminate existing sessions without deleting their rows.
- The user repository and authentication service gain update and collection operations, but their existing CLI
  consumers remain valid.
- ADR-0031's CLI-only provisioning and reset decision is superseded; its authentication, credential, session,
  cookie, and forced-password-change decisions remain accepted.
- Operational logs provide lightweight attribution but are not a tamper-resistant or application-queryable
  audit history. Deployments that require such a history need a later explicit decision.
- Self-service registration, email recovery, user deletion, project memberships, application settings, and
  external identity-provider administration remain out of scope.
