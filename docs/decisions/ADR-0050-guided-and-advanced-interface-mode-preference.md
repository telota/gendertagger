# ADR-0050: Guided and advanced interface-mode preference

**Status:** Accepted

## Context

The frontend delivery plan in `docs/24-frontend-delivery-plan.md` reduces the default navigation to one
project page with three actions (import, generate suggestions, review), so a new account can use the tool
immediately without first understanding the full method/aggregation/evaluation/export surface. Every
underlying capability described there remains in the backend and in the full navigation; the reduction is
a presentation choice, not a removal of functionality, membership role, or permission.

Some accounts — administrators, method authors, and users who already work with the full navigation — need
the existing complete sidebar unchanged. The choice between the reduced and the complete presentation must
persist per account across sessions and devices, must not be a role or a project setting, and must reuse
the existing preferences mechanism rather than create a second one.

[ADR-0043](ADR-0043-account-level-user-preferences.md) closed the account preferences resource to exactly
`locale`, `theme`, `desktop_sidebar_collapsed`, and `revision`, rejecting unknown fields by design. Adding a
field requires explicitly amending that closure rather than reopening or rewriting the immutable record.

## Decision

### Amendment to ADR-0043's closed contract

This decision partially supersedes ADR-0043's statement that the read and update contracts contain
exactly four fields. ADR-0043 remains otherwise in force: its ownership model, defaults-without-backfill
behavior, revision-based optimistic concurrency, authentication and forced-password gates, CSRF handling,
and migration discipline all apply unchanged to the field added here.

Add `interface_mode` to both `UserPreferences` and `UserPreferencesUpdate`:

| Field | Accepted values | Default |
|---|---|---|
| `interface_mode` | `"guided"` or `"advanced"` | `"guided"` |

`"guided"` presents the reduced per-project page and tab set described in `docs/24-frontend-delivery-plan.md`.
`"advanced"` presents today's complete navigation (D23–D25 baseline), unchanged. Both existing accounts
(via the column's `server_default`) and newly created accounts (via the Pydantic field default) resolve to
`"guided"` when no explicit preference has been saved, matching the project's decision to make the reduced
path the default experience rather than an opt-in.

`interface_mode` follows the same validation, omission, and conflict rules ADR-0043 already defines for
`theme`: a database `CHECK` constraint enforces the closed value set, omission in a PATCH preserves the
current value, and an explicit value outside `{"guided", "advanced"}` or an explicit `null` is rejected by
both the Pydantic contract and the database constraint. Unlike `locale`, `null` is not a valid value — there
is no "unresolved" state for interface mode.

### Scope

`interface_mode` is a presentation choice only. It must not gate API access, project membership, method
execution, or any other capability; every route and action it hides in the guided presentation remains
reachable over the API and in the advanced presentation. It does not change labels, normalization,
aggregation, certainty tiers, TEI output, or evaluation semantics.

Add an ordinary forward Alembic migration after the current head that adds the column with a
`server_default` of `"guided"` and its `CHECK` constraint, without backfilling a materialized preferences
row for accounts that have none. Regenerate the OpenAPI snapshot and frontend transport types in the same
change, per ADR-0043's established process.

## Consequences

- Accounts keep one existing preferences mechanism for all personal presentation choices instead of a
  second settings resource, reusing ADR-0043's concurrency, ownership, and validation guarantees.
- The guided/advanced split is purely presentational: removing or reintroducing sidebar entries in either
  mode is a frontend change and does not require a further backend contract change.
- Defaulting both existing and new accounts to `"guided"` means administrators and other accounts that
  expect the full navigation must explicitly switch to `"advanced"` once; this trade-off was chosen
  deliberately so every account's first experience is the reduced path.
- Verification covers the closed value set, default resolution for accounts with and without a saved row,
  omission versus explicit updates, invalid values at both the Pydantic and database layers, forward
  migration without drift, and OpenAPI/transport regeneration. Run the applicable locked quality gates and
  PostgreSQL integration checks from [`CONTRIBUTING.md`](../../CONTRIBUTING.md).
