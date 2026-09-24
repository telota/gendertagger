# Pydantic contracts

## Principle

Pydantic is the canonical language for typed contracts across the application. These contracts are not
SQLAlchemy persistence models. They are shared by FastAPI, application services, method adapters,
aggregation, import/export, configuration, Celery task envelopes, CLI operations, and tests.

Separate create, read, command, and internal models exist where mutability, provenance, or security boundaries
differ.

## Exact schema sources

The model source under [`src/gendertagger/models/`](../backend/src/gendertagger/models/) and
[`src/gendertagger/config/run.py`](../backend/src/gendertagger/config/run.py) defines exact fields, constraints, and
defaults. Public API schemas are generated from those models into the committed
[`OpenAPI snapshot`](../contracts/openapi-v1.json); the frontend transport is generated from that
snapshot.

This document records contract ownership and cross-field semantics that consumers must preserve. It does not
duplicate class bodies or field inventories.

## Contract ownership

| Module | Contract family |
|---|---|
| `config/run.py` | Run, method, aggregation, and execution configuration |
| `models/classification.py` | Labels, prediction status, certainty/agreement, prediction results |
| `models/lifecycle.py` | Persisted lifecycle status vocabularies |
| `models/person.py` | Person input, source-rich names/events, imported and persisted people |
| `models/project.py` | Projects, memberships, snapshots, manifests, import configuration |
| `models/method.py` | Method identity, version, and confidence-range descriptors |
| `models/run.py` | Runs, executions, batches, predictions, progress, SSE events |
| `models/aggregation.py` | Aggregation decisions, executions, results, method-result projections |
| `models/evaluation.py` | Evaluation definitions, executions, and reports |
| `models/export.py` | Export commands, executions, projections, and manifests |
| `models/review.py` | Annotations, history, review state, and review queries |
| `models/dispatch.py` | Durable typed dispatch-outbox contracts |
| `models/artifact.py` | Artifact records, lookup metadata, model manifests |
| `models/synchronous_classification.py` | Synchronous on-demand classification |
| `models/api.py` | Error envelopes and cursor pages |
| `models/user.py` | Global/project roles and provider-neutral user identity |
| `models/auth.py` | Local credentials, sessions, login, and password changes |
| `models/common.py` | UTC timestamps and canonical JSON hashing |
| `models/queues.py` | Internal queue-routing vocabulary |

## Shared model rules

Contracts reject unknown fields. Read models, commands, and task messages are frozen unless mutation is part
of their explicit purpose. Enum values are stable lowercase strings. Public field names use the vocabulary in
[`19-coding-and-documentation-style.md`](19-coding-and-documentation-style.md).

Cross-field invariants belong in model validators so API, service, CLI, and worker callers observe the same
rules. Services must not reconstruct those invariants from dictionaries or rely on database constraints as
their first validation boundary.

Canonical JSON uses sorted object keys, compact separators, unescaped Unicode, and finite JSON values. Hashes
are lowercase SHA-256 digests of those UTF-8 bytes. List order remains significant; object-key order does not.

## Classification and prediction

The controlled vocabularies and scientific meaning of labels, status, certainty, and agreement are defined in
[`07-methods-and-aggregation.md`](07-methods-and-aggregation.md). In particular, `unknown`, `abstain`, and
`error` remain distinct.

A successful prediction requires one canonical label. An abstention or error has no label. Raw labels, raw
output, and normalization metadata remain attached to the result so normalization is reproducible.

`method_confidence` is optional, finite, and valid only within the range declared by that method. It is not a
globally calibrated probability and cannot be compared or averaged across methods. The adapter boundary
validates the range before a Prediction can be persisted.

## People and import provenance

`tei_id` is required and is canonical only within a project snapshot. Historical source strings are preserved
rather than silently normalized.

Flat surname, forename, and alternate-name fields remain the stable classification and search projection.
Source-rich name forms preserve document order and distinguish structured from unstructured forms. When both
representations are present, validators require their deterministic projections to agree. Imported records
always carry structured forms; `name_forms` remains nullable for direct classification requests that supply
only the flat method inputs. See [ADR-0038](decisions/ADR-0038-derive-singleton-import-profiles.md).

Events preserve ordered source values. Source `<sex>` values are deliberately excluded from PersonInput so an
earlier annotation target cannot leak into classification input.

Every imported and persisted person carries the exact source-member name and record locator. Person-input
fingerprints include the complete profile-sensitive projection.

Public import requests declare format and packaging. The service derives the sole profile for that format and
persists it with resolved safety limits, so queued work is not reinterpreted after deployment settings change.
Unsupported format/packaging combinations fail validation rather than being inferred from filenames or media
types.
Source manifests are deterministic and bind ordered logical members to checksums, byte sizes, media types, and
artifact records. The complete import contract is defined in
[`08-ingestion-and-export.md`](08-ingestion-and-export.md) and
[ADR-0021](decisions/ADR-0021-versioned-multi-format-snapshot-ingestion.md).

## Method adapters

Each method has a stable lowercase snake-case identifier, immutable implementation and normalization versions,
and an optional declared confidence range. Operational routing and UI metadata do not belong in the scientific
descriptor; the method registry owns queue, batch, and artifact requirements.

Each adapter exposes its concrete Pydantic configuration model. The registry applies defaults and validates
configuration before persistence and execution. Lookup-backed methods select immutable artifacts by digest.

The batch adapter contract returns exactly one PredictionResult per input in the same order. Record-specific
scientific failures are results with `status=error`; batch-wide infrastructure or invalid adapter state raises
an exception so orchestration can apply retry policy. Missing assets or dependencies are permanent failures,
not transient retries.

## Aggregation

Reference aggregation returns a typed outcome that distinguishes a decided label, an unresolved substantive
tie, and no data. Fixed-shape vote counts, deterministic tied labels, authority override provenance, agreement,
and certainty remain part of the immutable result.

Validators enforce the edge contract: no-data has no votes or label; unresolved ties identify at least two
labels; override support counts occur together and remain internally consistent; and outcome, agreement tier,
certainty tier, and score cannot contradict one another. A lone local-LLM vote uses its categorical
self-reported certainty, never numeric method confidence.

An aggregation execution selects one run, a versioned strategy/configuration, and an exact ordered set of
completed method executions. Duplicate execution IDs are invalid. Run ID, ordered execution IDs, strategy,
and canonical configuration hash form the repeat-safe creation identity described by
[ADR-0034](decisions/ADR-0034-reuse-matching-aggregation-on-creation.md).

Per-person aggregation inputs preserve missing Prediction, explicit abstention, and technical error as three
different states. Lifecycle validators require consistent timestamps and failure diagnostics.

## Run configuration

Clients submit `RunConfig` as JSON in `POST /api/v1/runs`; the endpoint's OpenAPI operation contains the
canonical request example. Method identifiers are unique even when disabled, and nested values must be finite
JSON.

Before creating a Run, the server-side registry validates every method, applies adapter defaults, and produces
the fully resolved configuration. That object and its canonical hash are persisted. Workers load it from
PostgreSQL and never reinterpret client input.

## Task messages and dispatch

Celery messages are frozen identifier-only Pydantic envelopes. Workers load people, configuration,
predictions, artifacts, and lifecycle state from PostgreSQL or artifact storage; large scientific data,
filenames, paths, and storage URIs never travel through Redis.

The generic dispatch-outbox contract has one typed owner: task batch, aggregation execution, dataset snapshot,
evaluation execution, or export. Exactly one owner is present, its payload matches the owner type, and the
closed publisher mapping prevents target kind, task name, queue, owner, and payload from disagreeing. See
[`06-task-queue.md`](06-task-queue.md).

## Browser and API support

Public MethodExecution summaries exclude queue names and worker metadata. Progress counts are authoritative;
percentage is derived, and an unknown total remains representable.

Cursor pages require `has_more` and `next_cursor` to agree. Cursors are opaque and bound to their resource
scope, filters, and sort. Summary models support collection rendering while large raw scientific output stays
on detail resources.

Global and project roles are separate hierarchical vocabularies. CurrentUser remains authentication-provider
neutral and carries global roles only; project access is resolved per request and returned with accessible
project representations. See [ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md).

[ADR-0041](decisions/ADR-0041-admin-managed-teams-and-delegated-project-membership.md) defines
`TeamCreate`, `TeamUpdate`, `TeamSummary`, `TeamMember`, and `TeamMemberAdd`. `TeamCreate` normalizes a
required slug to its trimmed lowercase canonical form and preserves a validated nonblank display name.
`TeamUpdate` permits only a display-name patch: omission is a no-op and explicit `null` is invalid, so slugs
remain immutable. `TeamSummary` is roster-free; `TeamMember` is the global-administrator roster projection
with only team/user IDs, display name, active state, and membership creation time.

The delivered project/team contracts include `ProjectCreate.team_id`, optional
`initial_manager_user_id`, `ProjectEligibleUser`, `ProjectManagerUpdate`, manager-aware `ProjectMember`, and
`ProjectMembershipState`. `ManagedProjectSummary`, decided in
[ADR-0042](decisions/ADR-0042-management-only-project-discovery.md), is a separate non-scientific discovery
projection for a caller's current manager assignments. It includes only project identity, display identity,
and roster-free team identity; it does not imply an ordinary project role or expose project data. Manager-
facing candidates contain only `id` and `display_name`; account-directory projections and their security
metadata remain separate administrator contracts.

`AdminUser` is the global-administrator projection for a local account. It combines provider-neutral user
identity and roles with the non-secret local credential fields needed for administration. `AdminUserUpdate`
uses Pydantic field-set semantics so omitted fields remain unchanged while explicit `null` is invalid; username
is intentionally absent. `AdminUserPasswordResetResult` contains only the once-disclosed server-generated
temporary password. Password hashes and session state never enter these contracts. See
[ADR-0039](decisions/ADR-0039-administer-local-accounts-over-http.md).

Per-person method-result projections preserve the difference between an absent Prediction and a present
abstain/error result. Annotation history is newest first and must agree with the current annotation and review
revision.

Review commands append a new annotation only when `expected_revision` matches. Verify and correct actions
carry an explicit canonical label; defer carries no label. ReviewState is a workflow/concurrency projection,
not the scholarly history.

API errors use a stable envelope and client-facing codes even when internal exception classes change. Exact
public request and response shapes remain generated OpenAPI concerns; see
[`05-api.md`](05-api.md).

## Administrative settings contracts

`BrandingSettingField`, `BrandingEditableValues`, `BrandingOverrides`, `AdminSettings`,
`AdminSettingsUpdate`, and `AdminSettingsReset` are implemented and published through the administrative
settings API. Their normative specification is
[ADR-0040](decisions/ADR-0040-administrative-branding-overrides.md).

The editable allowlist contains exactly `institution_name`, `institution_url`, `contact_email`,
`privacy_notice_url`, `editors`, and `published_since_year`. ADR-0040 defines their types, validation, and
bounds; new administrative validation does not retroactively tighten startup environment configuration.

| Contract | Responsibility |
|---|---|
| `BrandingSettingField` | Closed enum of the six editable field names |
| `BrandingEditableValues` | All six resolved values, explicitly represented |
| `BrandingOverrides` | Sparse validated overrides that retain which fields were supplied |
| `AdminSettings` | `revision`, effective `branding: BrandingInfo`, `branding_defaults: BrandingEditableValues`, and `overridden_fields: list[BrandingSettingField]` |
| `AdminSettingsUpdate` | Required `expected_revision` and a nonempty partial `branding` update |
| `AdminSettingsReset` | Required `expected_revision` and a nonempty list of distinct `BrandingSettingField` values |

All contracts reject unknown fields. Omission in an update leaves the existing override unchanged. An
explicit `null` clears a nullable field and remains stored as an override; `editors: []` clears the ordered
editor list, while `editors: null` is invalid. Reset removes the selected override, exposing the current
deployment fallback. Serialization must preserve explicit nulls rather than dropping them alongside unset
fields.

`branding_defaults` contains the serving process's environment-resolved fallback, including application
defaults. Effective values resolve stored override, then environment, then application default. The public
`BrandingInfo` schema stays unchanged and receives no revision or override metadata. Infrastructure and
scientific configuration, secrets, and filesystem paths must never enter these administrative contracts.
`initiatives` and `legal_entity` remain deployment-managed, read-only branding; `logo_url` remains derived
and read-only.

## Serialization

Public `/api/v1` serialization uses `snake_case`, stable lowercase enum strings, UUID strings, and
timezone-aware ISO 8601 timestamps. `null` means absence and never substitutes for the substantive canonical
label `unknown`.
