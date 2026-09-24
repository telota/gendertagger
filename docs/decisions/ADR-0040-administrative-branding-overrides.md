# ADR-0040: Administrative overrides for deployment branding

**Status:** Accepted

Implementation status: persistence, administrative reads and writes, and public branding integration are
delivered in the backend slices. Frontend editing and active-view refresh remain pending. Delivery follows the
separate slices in [`15-implementation-plan.md`](../15-implementation-plan.md#administrative-settings-increment-adr-0040).

## Context

Administrators need to maintain a small set of publication details through the application.
[ADR-0036](ADR-0036-institution-branding-configuration.md) currently makes branding environment
configuration loaded once at API startup. [ADR-0039](ADR-0039-administer-local-accounts-over-http.md)
explicitly leaves application settings to a separate decision.

Existing settings have distinct lifecycles:

| Area | Current behavior | Consequence for this increment |
|---|---|---|
| API configuration | `create_app()` resolves `AppSettings` and constructs services once. | Environment changes require restarting affected processes. |
| Branding | Public routes read startup settings; the logo comes from a deployment-mounted file. | Branding currently has no database dependency. |
| Frontend branding | Each `useBranding()` consumer fetches on mount and can explicitly refresh. | Already-open views do not automatically reflect server changes. |
| Upload/import limits | `ProjectService` captures limits at construction; accepted snapshots persist resolved `SnapshotImportLimits` in `SnapshotImportConfig`. | Workers must continue using each snapshot's recorded limits; separate upload acceptance byte bounds are not part of that persisted limits object. |
| Proxy upload limit | Nginx independently caps the whole request body at `500M`. | An API setting cannot change the proxy limit; multipart overhead also consumes request-body space. |
| Worker configuration | Task service factories load `RuntimeSettings` lazily and cache services per process. | Worker tuning and infrastructure values do not refresh per task. |
| Session policy | The API captures `SessionLifetimePolicy`; login persists expiry times, while renewal uses process idle policy bounded by the persisted absolute expiry. | New and existing sessions react differently to policy changes; renewal never moves expiry backwards. |

These boundaries are implemented in
[`api/app.py`](../../backend/src/gendertagger/api/app.py),
[`services/projects.py`](../../backend/src/gendertagger/services/projects.py),
[`models/project.py`](../../backend/src/gendertagger/models/project.py),
[`services/snapshot_import.py`](../../backend/src/gendertagger/services/snapshot_import.py),
[`tasks/snapshot_import.py`](../../backend/src/gendertagger/tasks/snapshot_import.py),
[`services/authentication.py`](../../backend/src/gendertagger/services/authentication.py),
[`nginx.conf`](../../deploy/proxy/nginx.conf), and
[`useBranding.ts`](../../frontend/src/composables/useBranding.ts).

The first settings increment addresses publication metadata without changing execution policy or the
session behavior accepted in [ADR-0032](ADR-0032-sliding-session-lifetime.md).

## Decision

### Editable field allowlist

Permit administrative overrides for exactly six existing branding fields. The following validation
applies to new administrative writes. Existing environment configuration is not silently rewritten or
subjected to newly introduced startup requirements.

| Field | Purpose and type | Write validation and explicit clearing | Current consumers |
|---|---|---|---|
| `institution_name` | Publisher/operator display name; nullable string | Trim surrounding whitespace; 1-200 characters when present; reject blank strings and control characters. `null` clears it. | Footer, home publication block, legal notice |
| `institution_url` | Publisher link; nullable string | At most 2,048 characters; absolute HTTP(S) URL or same-origin path beginning with a single `/`; reject credentials, backslashes, and control characters. `null` clears it. | Footer |
| `contact_email` | Public contact address; nullable string | One syntactically valid mailbox address, at most 254 characters; no display-name wrapper, `mailto:` prefix, or query parameters. No network/deliverability checks. `null` clears it. | Footer, legal notice |
| `privacy_notice_url` | Privacy-notice link; nullable string | The same URL rules as `institution_url`. `null` clears it. | Footer, legal notice |
| `editors` | Ordered publication credits; list of strings | At most 50 entries; each trimmed, nonblank, 1-200 characters; reject control characters and duplicate trimmed entries. Preserve order. `[]` clears it; `null` is invalid. | Home publication block |
| `published_since_year` | Publication start year; nullable integer | Strict integer from 1 through the current UTC year at write time; reject booleans and numeric strings. `null` clears it. | Home publication block |

URLs are rendered as links and never fetched by the backend. All six fields share these rules:

- persist only explicit overrides;
- resolve stored override, then startup environment value, then application default;
- application defaults remain `null` for nullable fields and `[]` for `editors`;
- apply committed overrides to subsequent server reads without API or worker restarts;
- refresh or remount browser consumers before displaying the new values; and
- keep one deployment-wide value, not separate user or project values.

An explicit `null` or empty list is an override and suppresses a populated environment fallback.

### Other configuration

| Configuration | Classification |
|---|---|
| `initiatives`, `legal_entity` | Deployment-managed and visible as read-only branding. Editing their nested structures is deferred. |
| `logo_path` | Deployment-only; never expose its filesystem path. |
| `logo_url` | Derived and read-only; preserve the existing same-origin logo endpoint. |
| Upload/import limits | Deployment-managed; reuse `GET /api/v1/snapshot-upload-limits` without duplicating the fields in this resource. |
| Session idle and absolute-lifetime settings | Deployment-only; defer a separate read-only policy view until an operational need justifies it. |
| Database/broker addresses, credentials, filesystem paths, worker tuning | Deployment-only and outside this API. |
| Method, model, aggregation, import-profile, and other scientific configuration | Governed by existing domain contracts and persisted provenance. |

Editing `institution_name` does not change `legal_entity.name`; these remain separate facts. The API
never serializes `AppSettings` wholesale or accepts arbitrary configuration keys or client-selected paths.

### Canonical contracts and API

FastAPI remains the public interface. Pydantic defines closed contracts that reject unknown fields.
An application service resolves settings and owns mutation transactions; repositories expose canonical
models, never ORM rows. These contracts are accepted designs, not yet Python models or published OpenAPI
schemas; their implementation must update both the OpenAPI snapshot and generated frontend transport.

| Contract | Contents |
|---|---|
| `BrandingSettingField` | Enum containing exactly the six editable field names. |
| `BrandingEditableValues` | All six fields, explicitly represented. |
| `BrandingOverrides` | Sparse, validated representation preserving omitted fields versus explicit clearing. |
| `AdminSettings` | `revision`, effective `branding: BrandingInfo`, `branding_defaults: BrandingEditableValues`, and `overridden_fields: list[BrandingSettingField]`. |
| `AdminSettingsUpdate` | Required `expected_revision` and a nonempty partial `branding` update. |
| `AdminSettingsReset` | Required `expected_revision` and a nonempty list of distinct `BrandingSettingField` values in `fields`. |

`revision` and `expected_revision` are nonnegative integers. `branding_defaults` is the serving
process's environment-resolved fallback, including application defaults; it is not a copy of the
originally deployed configuration. `overridden_fields` includes fields explicitly cleared to `null`
or `[]` and contains each overridden field once.

| Endpoint | Behavior |
|---|---|
| `GET /api/v1/admin/settings` | Return `200 AdminSettings`. |
| `PATCH /api/v1/admin/settings` | Atomically set supplied overrides and return `200 AdminSettings`. |
| `POST /api/v1/admin/settings/reset` | Atomically remove selected overrides and return `200 AdminSettings`. |

Every administrative settings endpoint requires an authenticated global administrator who has satisfied
the forced-password-change requirement. Mutations also use existing CSRF protection. Responses use
`Cache-Control: no-store`.

Public `GET /api/v1/branding` remains unauthenticated and retains its `BrandingInfo` response shape.
After consumer integration it returns resolved branding without administrative metadata.

Example administrative read:

```json
{
  "revision": 3,
  "branding": {
    "institution_name": "Example Institute",
    "institution_url": "https://example.org",
    "logo_url": null,
    "editors": ["Example Editor"],
    "published_since_year": 2024,
    "initiatives": [],
    "contact_email": null,
    "privacy_notice_url": "https://example.org/privacy",
    "legal_entity": null
  },
  "branding_defaults": {
    "institution_name": "Deployment Publisher",
    "institution_url": "https://example.org",
    "contact_email": "contact@example.org",
    "privacy_notice_url": "https://example.org/privacy",
    "editors": ["Example Editor"],
    "published_since_year": 2024
  },
  "overridden_fields": ["institution_name", "contact_email"]
}
```

Here, `contact_email` is deliberately cleared despite a configured fallback. This update changes
the institution name and clears publication credits without changing unmentioned overrides:

```json
{
  "expected_revision": 3,
  "branding": {
    "institution_name": "Updated Institute",
    "editors": []
  }
}
```

Resetting removes an override and reveals the current deployment fallback. After that update, this
reset reveals `contact@example.org`:

```json
{
  "expected_revision": 4,
  "fields": ["contact_email"]
}
```

Resetting all settings requires listing all six enum values explicitly; there is no wildcard or
arbitrary-path operation. Errors use the existing API envelope:

- `401 authentication_required`: missing or invalid session;
- existing `403` errors: insufficient role, invalid CSRF, or required password change;
- `422 validation_error`: malformed values, unknown fields, invalid field selection, or an empty
  update/reset command;
- `409 settings_revision_conflict`: stale revision, with `expected_revision` and `current_revision`
  in safe error details; and
- `503 settings_unavailable`: settings storage cannot be read or written.

### Persistence and concurrent edits

Use one PostgreSQL table with exactly one deployment settings row:

| Column | Purpose |
|---|---|
| `id` | Fixed singleton identifier constrained to `1`. |
| `revision` | Nonnegative integer. |
| `branding_overrides` | Non-null JSONB object containing only the six permitted fields. |
| `updated_at` | UTC time of the last persisted change. |

JSONB stores a closed Pydantic-validated document, not arbitrary configuration. Database constraints
enforce the singleton identifier, revision bounds, and JSON object shape. Application validation
enforces the allowlist and value types on reads and writes.

The migration creates row `1` with revision `0` and `{}`; it does not copy environment values into
the database. Reads never initialize or mutate storage. A missing singleton after migration is an
operational error, not an empty settings state.

An absent key inherits, while a present key with JSON `null` explicitly clears a nullable field.
For example, `{}` and `{"contact_email": null}` must round-trip as different override documents.
Serialization must preserve explicit nulls.

Update and reset share one transaction protocol:

1. Lock the singleton row.
2. Compare its current revision with `expected_revision`.
3. Apply the requested change to the current override document and validate it.
4. Persist the complete document and increment the revision atomically.
5. Commit before reporting success or logging a successful change.

A matching-revision request that leaves the override document unchanged returns the existing revision.
A stale request still conflicts even if its requested values appear unchanged. Setting an override
equal to its fallback is a real change because it pins that value against later environment changes.
The revision tracks stored overrides only, not deployment/environment changes.

### Consistency, caching, and failure behavior

Read the singleton from the primary database once per settings/branding request. Do not add
process-local override caches, Redis invalidation, or background synchronization in this increment.
A read starting after a successful commit sees the committed overrides; an already-running request
may return the previous complete state.

All API replicas must use equivalent environment fallback configuration. Environment changes require
a coordinated rollout. Mixed fallback configurations can produce different effective values for
fields without overrides, even at the same database revision.

Public branding JSON also uses `Cache-Control: no-store` after integration. This prevents HTTP caching
but does not refresh Vue state already in memory. The later frontend slice must refresh active
branding consumers after administrative saves. Other browser sessions update on reload or remount;
live cross-browser propagation is deferred.

If settings storage is unavailable, administrative settings operations and public branding JSON
return `503 settings_unavailable`; they do not silently fall back to environment values that might
have been overridden or explicitly cleared. Admin writes never report success without a confirmed
commit. The logo endpoint remains filesystem-backed and independent of this settings read.

### Operational attribution

After a successful transaction, log the acting user ID, action (settings update or reset), request ID,
resulting revision, and changed field names. Do not log values, complete request bodies, credentials,
tokens, or database diagnostics containing sensitive configuration. A successful no-op may be logged
with an unchanged revision and empty changed-field list. No administrative history table or audit UI
is introduced.

### Relationship to ADR-0036

This decision partially supersedes ADR-0036's environment-only, startup-only behavior for the six
editable fields. Environment values remain fallbacks, database overrides take effect without restart,
and public branding JSON gains a database read when integration is implemented.

The public schema, unauthenticated access, absent defaults, deployment-neutral behavior, and
filesystem-backed logo remain unchanged. ADR-0036 retains its original decision text and Accepted
status; it is not superseded as a whole. Its remaining rules continue to apply.

## Consequences

Administrators can maintain publication details without a deployment once these slices ship. One row
and one revision mechanism provide atomic updates and predictable conflicts. The costs are a database
read for branding, coordinated deployment fallback changes, and explicit database-outage handling.
Legal-entity and initiative editing, logos, import policy, and session policy remain out of scope.

Database backups include branding overrides. Older application releases ignore them and display
environment branding, so rollout and rollback documentation must explain that behavior. Apply the
singleton migration before serving the new settings-backed API.

### Implementation scope

The authoritative sequence is in
[`15-implementation-plan.md`](../15-implementation-plan.md#administrative-settings-increment-adr-0040).
After this documentation-only increment, implement persistence and the administrative read API first,
then writes and public branding integration, and finally the frontend. Each slice stops for review
and a manual commit. No application code, migration, generated contract, or frontend work is delivered
by accepting this ADR.

### Acceptance criteria and future verification

Future verification must demonstrate:

- empty overrides reproduce existing environment-backed branding;
- all six fields follow the accepted validation and clearing rules;
- omission, explicit null, empty list, and reset remain distinct through persistence;
- unknown fields, arbitrary paths, and deployment-only settings are rejected;
- invalid updates change neither stored values nor revision;
- concurrent update/update and update/reset requests cannot silently overwrite each other, and stale
  revisions receive `409 settings_revision_conflict`;
- no-op behavior and migration initialization are deterministic, and reads never create the singleton;
- separate API instances observe committed overrides without restart when deployment fallbacks match;
- public branding retains unauthenticated access and its schema, with unchanged logo behavior;
- settings-storage failures return `503 settings_unavailable` without environment fallback, and failed
  writes produce no success log;
- logs contain attribution and field names without submitted values or secrets; and
- existing snapshots, scientific results, and session behavior remain unaffected.

The implementation needs model/service tests, PostgreSQL transaction and concurrency tests, API
authorization/CSRF tests, public-contract checks, and focused frontend tests. Follow the locked
static/build gates in [`CONTRIBUTING.md`](../../CONTRIBUTING.md). For this feature's agreed delivery
workflow, runtime suites and browser verification are reserved for the user's manual testing stage;
this documentation increment runs only the documentation checker and `git diff --check`.
