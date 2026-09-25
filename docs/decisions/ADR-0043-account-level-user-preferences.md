# ADR-0043: Account-level user presentation preferences

**Status:** Accepted

## Context

The bilingual client currently stores its locale choice in the browser, as required by
[ADR-0030](ADR-0030-bilingual-client-with-untranslated-canonical-vocabulary.md). Theme selection and
sidebar presentation are also personal choices. A local account should retain those explicit choices
across sessions and devices without changing project settings, deployment branding, or scientific
configuration.

The existing local account and session model from
[ADR-0031](ADR-0031-local-database-authentication.md) supplies ownership. A preferences resource must not
create another identity layer, weaken the forced-password-change gate, or turn
[ADR-0040](ADR-0040-administrative-branding-overrides.md)'s administrative settings into a general settings
store. Concurrent browser sessions need predictable conflicts, including the first save for an account
that has never saved preferences.

## Decision

### Ownership and closed contracts

Add one personal preferences resource owned by the existing local user account. Pydantic defines closed,
frozen read and update contracts with explicit typed fields; unknown keys are rejected. The read resource
contains exactly these fields:

| Field | Accepted values | Default |
|---|---|---|
| `locale` | `"de"`, `"en"`, or `null` | `null`, meaning browser default |
| `theme` | `"system"`, `"light"`, or `"dark"` | `"system"` |
| `desktop_sidebar_collapsed` | Strict boolean | `false` |
| `revision` | Strict nonnegative integer | `0` |

The update contract requires a strict nonnegative integer `expected_revision` and at least one of the
three preference fields. Booleans and numeric strings are not valid revisions. Omission preserves the
current value. Explicit `locale: null` clears an explicit language choice; explicit null is invalid for
theme and desktop-sidebar collapse. An owner ID, arbitrary key/value map, and project identifier are not
part of either public contract.

`locale: null` is stored and returned unresolved. The browser selects the first browser language whose
primary subtag is supported, then German if none is supported. The server never resolves browser-default
locale from request headers or replaces it with the effective language. `theme: "system"` similarly
remains a stored choice whose effective palette follows the browser's `prefers-color-scheme`.

`desktop_sidebar_collapsed` records only an explicit desktop choice. Responsive layout, viewport changes,
mobile drawers, and temporary navigation state must never write that field. Returning to a desktop layout
uses the saved desktop choice independently of the layout needed on a narrow screen.

### API and authentication

Expose `GET /api/v1/me/preferences` and `PATCH /api/v1/me/preferences`. Both return `200` with the full
canonical resource and use `Cache-Control: no-store`. PATCH returns only after a confirmed commit.

Ownership comes exclusively from the resolved `CurrentUser.id`. The principal must resolve to an active
existing local account with a current password; missing, invalid, expired, revoked, inactive, unresolved,
or non-local authentication receives the established `401 authentication_required` envelope. The existing
forced-password requirement returns `403 password_change_required`, and PATCH uses the existing session
CSRF validation with `403 forbidden` on failure. No global role, team membership, or project grant is
required. Administrators use the same self-service route and cannot select another account.

Malformed or empty updates return the established `422 validation_error` envelope. Stale writes return
`409 preferences_revision_conflict` in the existing error envelope, with `expected_revision` and
`current_revision` in its safe details. These endpoints belong to the password-current router, not the
limited authentication-recovery routes that a forced-password account can still reach.

### Persistence, defaults, and concurrency

Persist at most one preferences row per account, keyed by a foreign-key `user_id` to `users.id`. Locale,
theme, desktop-sidebar collapse, and revision are ordinary typed SQLAlchemy columns, not JSONB. Database
constraints enforce the closed value sets, required values, and nonnegative revision. SQLAlchemy rows
remain internal; repositories return canonical Pydantic models through application-service ports.

An account without a row has the documented default resource at revision `0`. GET performs no
initialization and never writes a preferences row. Existing accounts need no backfill. An unavailable
store must not be mistaken for an account without a row or cause a false successful save.

Application services own the unit of work and the commit. Every PATCH uses one transaction:

1. Lock the existing owning user row and freshly validate its local-account eligibility.
2. Read its preferences or construct the virtual defaults at revision `0`.
3. Compare `expected_revision` with the current revision before applying any update.
4. Apply only supplied fields and validate the complete resulting preferences.
5. If values changed, insert or update the row with the next revision and commit atomically; otherwise
   return the existing resource without changing its revision.

Locking the existing parent user row serializes concurrent initial writes even when no preferences row
exists. Two changed first writes carrying revision `0` cannot both succeed: after the first commit the
second sees revision `1` and conflicts. Existing-row updates use the same protocol. A matching no-op at
virtual defaults does not create a row; a stale no-op still conflicts. Returning all values to their
defaults after a save preserves the row and its increasing revision rather than resetting history to `0`.

Reads use committed database state and do not keep process-local preferences caches. A read beginning
after a successful commit observes that commit; an already-running read may observe the previous complete
resource. Preferences survive logout, session expiry, password changes, and administrative session
revocation; these operations must not reset presentation state. They do not enter scientific run
configuration, provenance hashes, Predictions, AggregatedResults, or export semantics.

Add an ordinary forward Alembic migration after the current head. Preserve the existing baseline and
migration history. The migration creates the table without copying browser state or materializing default
rows; database backups thereafter include saved account preferences.

### Relationship to ADR-0030 and frontend delivery

This decision explicitly partially supersedes ADR-0030's consequence that server-side locale persistence
is out of scope and the choice is stored only in the browser, for authenticated local accounts. ADR-0030
remains immutable, retains its original text and Accepted status, and continues to govern bilingual
catalogues, browser-language fallback, untranslated canonical vocabulary, and unsigned browser behavior.
No labels, normalization, aggregation, certainty, or other scientific semantics change.

The account resource becomes the authoritative saved preference state for authenticated local accounts.
Later client integration must scope cached resources to the principal, remove private cached state on
logout or account changes, preserve `null` and `"system"` as choices, and adopt canonical responses after
successful saves. It must reconcile a `409` against a fresh read instead of silently replaying an update
with a newer revision. Browser-local unauthenticated presentation may continue, but must not silently
migrate or overwrite an account's saved choices at sign-in.

This increment delivers backend persistence, contracts, endpoints, tests, the OpenAPI snapshot, and
regenerated frontend transport types. It does not build a settings page or connect existing client
presentation controls to account persistence. The frontend work is a later increment; `/admin/settings`
continues to manage deployment branding only.

## Consequences

- Explicit personal presentation choices can persist across sessions without granting access to another
  account or any project data.
- Virtual defaults avoid both an account backfill and writes on reads. A single revision provides atomic
  updates and visible conflicts at the cost of reconciling simultaneous changes to different fields.
- A user-row lock provides safe initialization with the supported PostgreSQL database and existing unit of
  work rather than an insert race or a last-write-wins upsert.
- A later SSO account model needs an explicit extension of eligibility; provider-neutral principals alone
  do not create local accounts or preference owners.
- Verification covers defaults and read-only initialization, persistence across sessions, account isolation,
  strict validation, omission and locale clearing, no-ops, authentication and forced-password gates, CSRF,
  stale revisions, concurrent initialization, forward migration, and OpenAPI/transport drift. Run the
  applicable locked quality gates and PostgreSQL integration checks from
  [`CONTRIBUTING.md`](../../CONTRIBUTING.md).
