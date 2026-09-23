# ADR-0031: Local database authentication backend

**Status:** Accepted

The fixed 8-hour session lifetime, the `LoginRequest` shape, the `401` for a wrong current password, and the
anticipated hashing settings in this decision are superseded by
[ADR-0032](ADR-0032-sliding-session-lifetime.md). Credential and session storage, cookie names, the CSRF
scheme, CLI provisioning, and the password-change gate remain accepted.

## Context

[`13-auth-and-security.md`](../13-auth-and-security.md) defines `AuthenticationBackend` as a provider-neutral
protocol (`authenticate`, `validate_csrf`) so every provider terminates into the same `CurrentUser`
principal. The shipped `RejectAllAuthenticationBackend` fails closed by design and blocks the browser
client: [`24-frontend-delivery-plan.md`](../24-frontend-delivery-plan.md) records the choice of production
provider as D1, the last blocking decision, and its own recommendation was to implement a local account
backend now and treat institutional OIDC/SSO as a later, contained backend swap rather than wait on it.

`UserRow` ([`db/reviews.py`](../../src/gendertagger/db/rows/reviews.py)) already models a provider-neutral user
with global roles ([`13-auth-and-security.md`](../13-auth-and-security.md)) but carries no credential or
session concept, deliberately — those are provider-specific.

The v1 scope exclusions already rule out self-service account creation and email-based password recovery:
neither appears in the wireframe, and the repository has no outbound mail dependency today. Provisioning is
therefore an administrative act, not a public endpoint.

## Decision

Ship `DatabaseAuthenticationBackend`, a local-account implementation of `AuthenticationBackend` backed
entirely by Postgres. No JWT, no external identity provider.

**Provisioning.** Accounts are admin-provisioned only, and provisioning is a CLI concern, not an API
endpoint — no v1 frontend screen manages users or projects settings (both are explicit v1 scope
exclusions), so an HTTP surface for it would have no caller. `gendertagger users create` (existing
`UserCreate`, extended with a local credential) and `gendertagger users reset-password` run against the
database directly, the same way `gendertagger assets ...` already provisions method lookup data. Both set
or generate an initial password and flag the account `must_change_password`; reset additionally revokes
every existing session for that user. There is no public registration endpoint and no email-based reset
flow.

**Credentials.** A new `user_credential` table, one row per local-account user, separate from `UserRow` so a
future SSO-provisioned user carries no credential row:

- `user_id` — primary key, FK to `users.id`
- `username` — unique, case-insensitive login identifier; local-account-specific, so `User`/`CurrentUser`
  stay provider-neutral and unchanged
- `password_hash` — Argon2id via a pinned exact-version hashing dependency, per the direct-dependency
  pinning policy in [`18-engineering-and-quality.md`](../18-engineering-and-quality.md)
- `must_change_password` — boolean, default `true` on creation and on admin reset
- `updated_at`

**Sessions.** A new `user_session` table. Sessions are server-side state, not a signed/stateless token, so
a session is revocable by deleting or marking its row:

- `id` — primary key; the value stored is a SHA-256 hash of the random session token, never the token
  itself, mirroring the repository's existing content-addressed-artifact caution around not persisting
  secrets in the clear
- `user_id` — FK
- `csrf_secret` — random, independent of the session token
- `created_at`, `expires_at` — fixed absolute TTL from creation (configurable, default 8 hours; no sliding
  refresh — re-authenticate after expiry)
- `revoked_at` — nullable; set on logout, admin password reset, or admin-initiated revocation

**Cookies.** Same-origin, matching [`13-auth-and-security.md`](../13-auth-and-security.md):

- `session` — the raw session token, `HttpOnly`, `Secure`, `SameSite=Lax`
- `csrf_token` — the session's `csrf_secret`, **not** `HttpOnly` (the SPA reads it and mirrors it into the
  `X-CSRF-Token` request header per the frontend transport-layer rule that CSRF attachment is centralized),
  `Secure`, `SameSite=Lax`

`authenticate()` hashes the incoming `session` cookie value, looks up an unrevoked, unexpired
`user_session` row, and returns its `user_id`. `validate_csrf()` compares the `X-CSRF-Token` header against
the session row's `csrf_secret` with a constant-time comparison.

**Endpoints** (new `gendertagger.api.auth` router, `/api/v1/auth/*`):

- `POST /api/v1/auth/login` — `{username, password}`, unauthenticated, exempt from CSRF (no session exists
  yet). Verifies the Argon2id hash, issues a session, sets both cookies, returns `CurrentUser`. Failure is a
  generic `401 invalid_credentials` regardless of whether the username exists, to avoid enumeration.
- `POST /api/v1/auth/logout` — authenticated, CSRF-protected. Revokes the current session, clears both
  cookies.
- `POST /api/v1/me/password` — authenticated, CSRF-protected, self-service. Requires the current password,
  sets a new one, clears `must_change_password`.

**`must_change_password` gate.** While set, every `/api/v1` endpoint except `GET /me`,
`POST /auth/logout`, and `POST /me/password` returns `403 password_change_required`, mapped on the client
through the existing stable-`code` error handling, not a message match.

Rate limiting and lockout on repeated failed logins are explicitly deferred — noted as follow-up, not built
in this change, to keep the shipped surface to what "simple, DB-based" actually requires.

## Consequences

- Unblocks M0/M2 of the frontend delivery plan: the client has a real, non-`RejectAll` backend to
  authenticate against, and D1 is resolved.
- No new runtime dependency beyond a pinned password-hashing library; no outbound email, no external
  identity provider, no JWT verification surface.
- `CurrentUser` and the authorization dependencies (`require_viewer`/`require_reviewer`/`require_operator`)
  are unchanged — the contained-change property the plan predicted holds.
- Sessions are revocable server-side (admin reset, logout, expiry), which a stateless token would not give
  for free.
- A later institutional SSO provider is an additional `AuthenticationBackend` implementation and does not
  require touching `user_credential`; existing local accounts and SSO accounts can coexist, since
  credentials are keyed off `user_id`, not baked into `UserRow`.
- New migration for `user_credential` and `user_session`; new settings for session TTL and the hashing
  parameters.
- Deferred and tracked as follow-up: login rate limiting/lockout, and any self-service password recovery
  (would require adding outbound email infrastructure the repository does not currently have).
