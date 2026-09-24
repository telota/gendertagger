# ADR-0032: Sliding session lifetime with an opt-in persistent sign-in

**Status:** Accepted

## Context

[ADR-0031](ADR-0031-local-database-authentication.md) gave every local-account session a fixed absolute
lifetime of 8 hours from login, with no refresh. Planning the application shell (milestone M2 in
[`24-frontend-delivery-plan.md`](../24-frontend-delivery-plan.md)) exposed the consequences:

- An active reviewer is signed out exactly 8 hours after login, in the middle of work. Activity does not
  count; the next request simply fails with `401`.
- [`25-frontend-design-guidelines.md`](../25-frontend-design-guidelines.md) requires time limits to satisfy
  WCAG 2.2.1. An 8-hour limit is below the criterion's 20-hour exception, so the client would need a
  pre-expiry warning and an extension by a simple action. The API exposed neither the expiry time nor a way to
  extend a session, and signing in again is not a simple action.
- The 8 hours had no stated basis. NIST SP 800-63B (revision 3) asks single-factor sessions (AAL1) to
  reauthenticate at least every 30 days; the 12-hour and 30-minute limits belong to multi-factor AAL2. Local
  accounts are single-factor. The risk a web session carries is also limited: provisioning and password
  resets are global-administrator actions behind the standard CSRF and password-current gates, a password
  change requires the current password, and annotations are append-only and attributed, so a wrong one is
  traceable and superseded rather than lost.
- Shared workstations, such as a reading room, are plausible. A reviewer there needs a session that does not
  outlive the browser.

Planning also surfaced three smaller gaps in ADR-0031's contract:

- `POST /auth/login` returns `CurrentUser`, which does not carry the forced-password-change flag. The client
  learned about it only from a `403 password_change_required` on some later call.
- A wrong current password on `POST /me/password` returned `401 invalid_credentials`, the same status as a
  lost session, so a client that answers `401` by signing the user out would do so over a typo.
- ADR-0031 anticipated settings for the password-hashing parameters. None were added.

## Decision

**Two kinds of session, chosen at login.** `LoginRequest` gains `keep_signed_in: bool`, default `false`. The
login form offers it as a "keep me signed in" checkbox, unchecked by default.

| | `keep_signed_in: false` | `keep_signed_in: true` |
|---|---|---|
| Cookies | Browser-session cookies without an expiry; the browser discards them when it closes | Persistent cookies that expire at the session's absolute limit |
| Idle limit | 24 hours | 7 days |
| Absolute limit from login | 30 days | 30 days |

Both cookies of a session, `session` and `csrf_token`, carry the same expiry. Their names, flags, and the
CSRF scheme are unchanged from ADR-0031.

**Sliding idle expiry.** `user_sessions.expires_at` becomes the idle expiry, and a new
`absolute_expires_at` records the absolute limit fixed at login. Each authenticated request moves
`expires_at` to `min(now + idle limit, absolute_expires_at)`. The move is persisted only when it advances
`expires_at` by at least five minutes, so an active session costs at most one write per five minutes, and
the update is conditional so concurrent requests never move it backwards. A session is valid while
`revoked_at` is null and `expires_at` is in the future. A database check constraint keeps
`expires_at <= absolute_expires_at`.

Three settings replace `GENDERTAGGER_SESSION_TTL_SECONDS`:

- `GENDERTAGGER_SESSION_IDLE_SECONDS`, default 86 400 (24 hours);
- `GENDERTAGGER_SESSION_KEEP_SIGNED_IN_IDLE_SECONDS`, default 604 800 (7 days);
- `GENDERTAGGER_SESSION_MAX_LIFETIME_SECONDS`, default 2 592 000 (30 days).

**Migration.** Revision `20260921_0003` adds `keep_signed_in` (default `false`) and `absolute_expires_at` to
`user_sessions`. Existing sessions are backfilled with `absolute_expires_at = expires_at`, so each keeps
its original end and is never extended.

**Session state endpoint.** `GET /api/v1/auth/session` returns `CurrentSession`
(`must_change_password`, `keep_signed_in`). Like `GET /me`, it is authenticated and exempt from the
password-change gate, so the client can learn about a forced change right after login or on page load.
`CurrentUser` stays unchanged and provider-neutral.

**Wrong current password.** `POST /me/password` answers a wrong current password with
`400 invalid_current_password`. A `401` from the API now always means that no valid session exists.

**Hashing parameters stay fixed in code.** Argon2id uses the pinned library's vetted defaults and is not
configurable. This replaces ADR-0031's anticipated hashing settings: a setting whose only effect would be
to weaken the hash is not worth offering.

**No expiry warning.** Every limit of either kind exceeds 20 hours, so WCAG 2.2.1's 20-hour exception
applies. The API does not expose expiry times, and the client shows no pre-expiry warning. The client must
still recover from a `401` at any moment, since a session also ends through its idle or absolute limit, a
logout elsewhere, or an administrative password reset: it keeps the unsent decision, offers an inline
sign-in, and retries.

## Consequences

- An active reviewer is never signed out mid-work, except at the 30-day absolute limit.
- Browsers that restore the previous session (Chrome's and Firefox's "continue where you left off") keep
  browser-session cookies across restarts. For an unchecked session on a shared machine left signed in, the
  24-hour server-side idle limit is therefore the real bound, not the browser closing. A shorter unchecked
  idle limit was considered; 24 hours was chosen so that both kinds fall under the 20-hour exception without
  relying on WCAG's "adjust" provision.
- Background requests count as activity. A tab left polling a long-running run, or reconnecting its progress
  stream, keeps its session alive up to the absolute limit. Accepted, because the absolute limit bounds it.
- A stolen session cookie, together with the readable CSRF cookie, stays usable as long as it is used, up to
  30 days. Revocation is unchanged: logout ends one session and an administrative reset ends all of a user's
  sessions. Login rate limiting stays deferred in
  [`22-future-development.md`](../22-future-development.md).
- Rejected alternatives: keeping the fixed 8 hours and adding a warning dialog with an extension endpoint
  (interrupts active users and adds client and API surface), and a user-triggered extension capped at
  24 hours (still interrupts active work once a day).
- ADR-0031's credential and session storage, cookie names, CSRF scheme, CLI provisioning, and
  password-change gate remain accepted.
