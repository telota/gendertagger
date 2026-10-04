# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project intends to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). No tagged release exists yet; the
packaged version remains `0.0.0` while the vNext scaffold described in [`SPEC.md`](SPEC.md) is implemented.

## [Unreleased]

The repository was reset from the legacy research pipeline to a code-empty implementation scaffold, and the
accompanying paper was revised. See [`docs/15-implementation-plan.md`](docs/15-implementation-plan.md) for
the phased plan that resumes application code.

### Added

- vNext specification and contributor entry points: [`SPEC.md`](SPEC.md), [`PLAN.md`](PLAN.md),
  [`AGENTS.md`](AGENTS.md), [`CONTRIBUTING.md`](CONTRIBUTING.md), and the
  former `SCAFFOLD.json` design manifest.
- Twenty numbered design documents under [`docs/`](docs/), indexed by
  [`docs/00-design-index.md`](docs/00-design-index.md), covering architecture, domain model, Pydantic
  contracts, persistence, API, task queue, methods and aggregation, ingestion/export, annotation and review,
  evaluation, provenance, deployment, auth, testing, frontend integration, and style.
- Six Architecture Decision Records under [`docs/decisions/`](docs/decisions/), recording the choice of a
  Pydantic/FastAPI core, immutable dataset snapshots, the reference aggregation strategy, the
  PostgreSQL/Celery/Redis stack, local-first data processing, and the Vue browser-client boundary.
- Package layout under `src/gendertagger/` for the planned `api`, `cli`, `config`, `db`, `domain`,
  `evaluation`, `export`, `ingestion`, `methods`, `models`, `services`, `storage`, and `tasks` modules.
- Canonical Pydantic v2 person and prediction contracts, including the label, status, certainty, and
  agreement vocabularies and validation of prediction-result invariants.
- Validated run configuration contracts with safe YAML loading, duplicate-key detection, canonical JSON,
  and deterministic SHA-256 provenance hashes.
- Typed method-adapter protocol and frozen minimal method descriptors, including adapter-owned Pydantic
  configuration models, result-cardinality checks, declared confidence-range validation, and explicit
  record-level versus batch-level failure semantics.
- Pure, versioned raw-label normalization profiles for all ten methods, preserving raw evidence and the
  canonical distinction among substantive `unknown`, abstention, and technical failure.
- Pure `reference_v1` aggregation with strict reference-method completeness, authority priority, unweighted
  pooled votes, deterministic unknown tie-breaking, transparent substantive ties, and override support counts.
- Deterministic agreement scoring and certainty assignment for pooled votes, authority overrides, transparent
  ties, no-data outcomes, and lone voters with typed local-LLM self-reported certainty.
- Paired `legacy_characterization` and `reference_v1` golden fixtures plus end-to-end domain regression tests
  from observed raw labels through normalization, voting, agreement, and certainty.
- Contract tests for validation, serialization, source-string preservation, isolated mutable defaults,
  and the semantic distinction between `unknown`, `abstain`, and `error`.
- Repository policy gates: `scripts/check_documentation.py`, `scripts/check_contract_naming.py`,
  `scripts/check_package_initializers.py`, and `scripts/check_distribution.py`.
- Test scaffold under [`tests/`](backend/tests/) with a packaging smoke test and policy-script regression tests.
- A validated run-creation JSON example in the committed OpenAPI contract, plus deployment, frontend, and
  persistence placeholders in [`frontend/README.md`](frontend/README.md), `migrations/`, and `deploy/`.
- Reproducible dependency management via `uv.lock`, hatchling builds, and PEP 735 dependency groups.
- Authenticated FastAPI `/api/v1` resources for projects, immutable TEI snapshot imports, runs, the method
  registry, aggregations/results, append-only annotations, and server-filtered review lists; public contracts
  include cursor pagination, normalized error envelopes, a committed OpenAPI snapshot, and typed `CurrentUser`.
- A structured TEI import profile that preserves ordered regular and alternate name forms, records name-form
  provenance in immutable snapshots, and safely extracts direct GND and VIAF identifiers.
- Celery/Redis asynchronous execution: a boundary-clean Celery app and worker composition, a runnable
  parenthetical-qualifier method adapter on the CPU queue, reproducible per-batch person slices, idempotent
  batch execution with retry/backoff and permanent-versus-transient failure classification, guarded run and
  method-execution lifecycle transitions, aggregate progress on run and execution resources, a
  `POST /runs/{run_id}/executions` trigger, and a reconnect-safe `GET /runs/{run_id}/events` SSE stream.
- Generic asynchronous aggregation execution through the transactional outbox, with identifier-only CPU work,
  at-least-once publication and atomic claims, strict per-person reference-method completeness, no synthetic
  Prediction evidence, and atomic complete-result persistence for the current corpus scale.
- Asynchronous DatasetSnapshot import through the same transactional outbox, with durable source staging
  before `202 Accepted`, an identifier-only CPU-worker envelope, duplicate-safe claims, and atomic streamed
  PersonRecord persistence that rolls back completely before retry or terminal failure.
- Explicit, versioned snapshot format, packaging, profile, manifest, source-member, and resolved-limit
  contracts supporting single, loose, ZIP, and TAR.GZ TEI sources plus single CSV, XLSX, and JSON sources.
- Strict TEI-equivalent tabular ingestion with the exact `xml:id`, `persName`, `birth`, `death`, `event`,
  `note`, and `idno` fields; native JSON arrays or JSON-valued CSV/XLSX cells preserve multiple forenames,
  ordered alternative names, events, and typed GND/VIAF/Wikidata identifiers without spreadsheet coercion.
- The `tei_p5_person_register` / `tei_parser_v3` profile adds ordered events, safe descendant-text
  boundaries, and supported-inline-markup validation.
- Shared strict TEI/tabular authority normalization with exact host/path matching, typed bare/URI parity,
  conflict and duplicate rejection, spoofed-host protection, bounded JSON integer decoding, and permanent
  JSON/CSV U+0000 validation.
- Secure archive and workbook readers with deterministic member ordering, traversal/link/special-member and
  active-workbook rejection, pre-allocation ZIP/ZIP64 directory bounds, secure OOXML metadata preflight,
  read-only XLSX streaming, expansion ceilings, compression-ratio checks, and collection-wide TEI-ID
  uniqueness.
- Immutable loose-source manifests, ordered source-member Artifact provenance, and record-level source member
  and locator attribution. TEI v3 now preserves ordered direct events while source `<sex>` labels remain
  excluded from PersonInput to prevent target leakage.
- Immutable ready-snapshot inventory statistics now materialize during import and expose total people, direct
  TEI `<gender>` coverage and value distribution, GND coverage, and their intersection through
  `GET /snapshots/{snapshot_id}/statistics`. The dataset detail view presents those counts and marks each
  person-list row with GND availability; legacy snapshots report source-gender coverage as not captured
  instead of a false zero.
- A pinned official Pyright CLI and shared editor/CI configuration, complementing strict mypy with a second
  required static-analysis implementation.
- Server-side uncertainty-first review ordering. `GET /api/v1/review-items` accepts `sort=uncertainty` (the
  new default) or `sort=tei_id`, where `uncertainty` applies the versioned `review_triage_v1` rank recorded in
  [ADR-0022](docs/decisions/ADR-0022-uncertainty-first-review-ordering.md): contested, low, uncertain, single,
  and no-data records first, then authority-vs-ensemble disagreement and technical prediction errors, then
  confident records. Every rank input is immutable for a completed aggregation, so annotating a record never
  moves it between cursor pages.
- `AggregatedResult.has_prediction_error`, a persisted projection of the immutable prediction evidence that
  makes the triage rank a function of one row instead of a correlated subquery. The accompanying migration
  backfills existing results from their member method executions.
- Content-addressed method-data provisioning for Wiki-Gendersort, HIVOTO, and GND: retained source artifacts,
  deterministic compiled SQLite lookups, digest-only run configuration, scheduler-sealed
  `MethodExecution.data_artifact_id` provenance, verified read-only worker materialization, batched lookup
  adapters, an offline MARC21-XML GND builder with entity-type evidence, and explicit CLI acquisition commands.
- `hf_distilbert` and `hf_genderize` transformer-classifier adapters completing seven of the nine reference
  pooled/authority methods. Each Hugging Face model is provisioned as a content-addressed multi-file model
  manifest that extends the lookup-asset provenance boundary to native model directories (see
  [ADR-0024](docs/decisions/ADR-0024-hf-transformer-model-manifest-adapters.md)), materialized read-only and
  offline by a dedicated worker-side directory resolver, and classified per forename token through the shared
  name-token consensus, with a new `assets prepare-hf-model` CLI provisioning command and `transformers`
  optional dependency extra.
- Experimental `hivoto_xgboost` adapter (excluded from the reference vote): a two-stage, per-forename-token
  classifier that checks the already-compiled `hivoto_lookup` artifact first and falls back to a trained
  TF-IDF character-n-gram + XGBoost model, reduced by a bespoke consensus ported from the legacy reference
  script (see [ADR-0025](docs/decisions/ADR-0025-hivoto-xgboost-adapter.md)). Reuses the multi-file model
  manifest mechanism introduced for the transformer classifiers, with its lookup member materialized from an
  already-registered `hivoto_lookup` digest rather than recompiled. The trained model was converted once,
  losslessly, from its original pickled form to pickle-free JSON (see
  `data/models/hivoto_xgboost/PROVENANCE.md`), verified byte-exact against the original, and committed
  directly since it was trained by this project rather than externally licensed. Adds a new
  `assets prepare-hivoto-xgboost` CLI command and `hivoto-xgboost` optional dependency extra.
- Local database authentication as the default `AuthenticationBackend`
  ([ADR-0031](docs/decisions/ADR-0031-local-database-authentication.md)): admin-provisioned accounts through
  `gendertagger users create` and `users reset-password`, Argon2id password hashes, revocable server-side
  sessions with a fixed configurable lifetime, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, and
  `POST /api/v1/me/password`, a forced password change on new and reset accounts
  (`403 password_change_required`), and a migration adding `user_credentials` and `user_sessions`.
- The Vue 3 + TypeScript + Vite client scaffold in [`frontend/`](frontend/) (milestone M1): transport types
  generated from the committed OpenAPI snapshot with a CI drift check, a typed fetch client with CSRF
  attachment and stable-code error mapping, German and English message catalogues
  ([ADR-0030](docs/decisions/ADR-0030-bilingual-client-with-untranslated-canonical-vocabulary.md)),
  theme-scoped design tokens for both themes, automated accessibility and contrast checks, a pinned
  multi-stage image with a history-mode fallback, and `frontend_*` CI jobs and pre-commit hooks.
- `scripts/update_openapi_snapshot.py`, which owns the one rendering of the committed OpenAPI snapshot. It
  rewrites `tests/fixtures/openapi-v1.json`, and with `--check` it is what the contract test runs, so a stale
  snapshot now fails with the commands that fix it instead of a bare string diff.
- `GET /api/v1/projects`, a cursor-paginated list of the projects the caller has a role in, and admin-only
  `GET`, `PUT`, and `DELETE /api/v1/projects/{project_id}/members[/{user_id}]` plus the
  `gendertagger projects add-member`, `remove-member`, and `list-members` CLI commands for managing
  project memberships ([ADR-0033](docs/decisions/ADR-0033-project-scoped-membership-roles.md)).
- `GET /api/v1/aggregations/{aggregation_id}/results/{result_id}/predictions`, which returns every selected
  method's immutable prediction for the person behind one result, in selection order, with a null
  `prediction` where a method persisted none, and `GET /api/v1/annotations?snapshot_id=&tei_id=`, which
  returns a person's review state with the complete annotation chain, newest first and attributed by
  reviewer display name. They are the last of the three read endpoints blocking the review client.
- Cursor-paginated, newest-first collections for navigating the resource tree:
  `GET /api/v1/projects/{project_id}/snapshots`, `GET /api/v1/snapshots/{snapshot_id}/runs`, and
  `GET /api/v1/runs/{run_id}/aggregations`, `/evaluations`, and `/exports`. Each lists its resources in every
  lifecycle state, so a client can recover identifiers after a reload.
- `GET /api/v1/aggregations/{aggregation_id}/review-summary`, which counts a completed aggregation's results
  by certainty tier, agreement tier, current review state, final label, and review action in one grouped
  read, with the same joins as `review-items`, so a client can size a review queue, fill dashboard tiles, or
  read the verified-versus-corrected breakdown without paging. The response also carries
  `last_annotated_at`, the most recent review activity in the aggregation.
- `PUT /api/v1/projects/{project_id}/working-aggregation`, which points a project at one of its own completed
  aggregations for its dashboard and review queue to summarize, or clears the pointer, gated to project
  operators ([ADR-0035](docs/decisions/ADR-0035-project-working-aggregation.md)). `AccessibleProject` carries
  the nullable `working_aggregation_execution_id`.
- `GET /api/v1/snapshot-upload-limits`, which returns the deployment's `SnapshotUploadLimits`: the per-part
  and aggregate upload byte bounds that produce `413`, and the `SnapshotImportLimits` a newly accepted
  snapshot records. The values come from the service that enforces them, so a client can check a selection
  before uploading.
- Optional Vue game mode for reviewers on completed aggregations: 10-, 20-, or 50-question rounds use the
  ordinary annotation command, expose optional personal timer and streak feedback, and reveal machine evidence
  only after each saved answer. The default pool contains open decisions in server triage order; an
  entire-dataset variant includes previously reviewed entries and advances through cursor pages in stable
  source-ID order. Idempotent `POST /projects/{project_id}/game-rounds` accepts only saved annotation IDs and
  derives a server-verifiable score of ten points per accepted annotation; browser timing, skips, and streaks
  cannot affect the persistent project leaderboard. New projects default to disabled game mode; project
  operators can enable or disable it from the overview without deleting rounds or affecting scientific results.

### Changed

- The Python project moved into [`backend/`](backend/), a sibling of `frontend/`: `src/`, `tests/`,
  `migrations/`, `scripts/`, `config/`, `pyproject.toml`, `uv.lock`, `alembic.ini`, and the Pyright tooling.
  Backend commands now run from `backend/`; the backend image builds from `backend/` as its context; CI,
  pre-commit, compose, and the documentation follow. The compose-level `backup.sh`, `restore.sh`, and
  `test_migration.sh` moved to `deploy/scripts/`. The source distribution now contains only backend files.
- The OpenAPI snapshot moved from `tests/fixtures/openapi-v1.json` to [`contracts/`](contracts/), a neutral
  folder for artifacts both apps depend on, so the frontend no longer reads a backend test fixture.
- The five Alembic revisions are squashed into the single baseline `20260815_0001`; a `pg_dump
--schema-only` of the squashed baseline is identical to the old chain. The data steps of `20260921_0003`
  and `20260921_0004` and their migration tests are gone, since no deployed database needs them. A local
  database migrated to `20260922_0005` moves over with `alembic stamp --purge 20260815_0001`. See the
  migration policy in [`docs/04-persistence.md`](docs/04-persistence.md).
- The dispatch outbox table is renamed from `batch_dispatches` to `dispatch_outbox`, since it carries all
  five dispatch kinds; its constraints, indexes, and stored status enum follow, and `BatchDispatchStatus` and
  `BatchDispatchRow` become `DispatchStatus` and `DispatchOutboxRow`. Edited in the baseline, per the migration
  policy.
- `export_id` is renamed to `export_execution_id`, matching `aggregation_execution_id` and
  `evaluation_execution_id`: in the `GET /api/v1/exports/{export_execution_id}` and `/download` path parameters
  (public contract: parameter name and operation IDs only; the URLs keep their shape), `ExportTaskMessage`, the
  export manifest, and the `artifacts` and `dispatch_outbox` columns. The outbox constraint becomes
  `export_execution_single_dispatch`.
- The database now seals failed dataset snapshots like ready ones: their status and failure details can no
  longer be updated, and they cannot be deleted. Edited in the baseline, per the migration policy.
- Runs and dataset snapshots record `failure_class`, like every other execution resource: the exception class
  for a failed snapshot import, and `MethodExecutionFailure` for a run failed by its method executions.
  `Run` and `DatasetSnapshot` gain the nullable field (additive contract change); the database allows it only
  on failed rows. Edited in the baseline, per the migration policy.
- The `POST /classify` response documented `certainty_tier` and `agreement_tier` with tier values that do not
  exist (`medium`, `strong`, `moderate`, `low`). Both descriptions are now generated from `CertaintyTier` and
  `AgreementTier`, so they list the real values and cannot drift again. Description text only; field types
  were already correct.
- Evaluation and export executions now have the same database guards as aggregation executions: legal
  lifecycle transitions only, no deletes, immutable creation-time provenance, sealed terminal rows, and
  insert-only evaluation membership limited to completed executions of the same run. Edited in the baseline,
  per the migration policy.
- The export manifest records its format as `version: 1`, like `SourceManifestV1`, so later changes to its
  persisted fields are detectable.
- `review-items` filters on certainty tier, agreement tier, and review state now take several values, as
  repeated `certainty_tiers`, `agreement_tiers`, and `workflow_states` query parameters that match any listed
  value. They replace the single-valued `certainty_tier`, `agreement_tier`, and `workflow_state` parameters,
  so each of the two review queues is one ordered query. Values are kept in vocabulary order for the cursor
  scope, and a repeated value is rejected.
- `POST /api/v1/runs/{run_id}/aggregations` now returns an existing aggregation with the same run, strategy,
  configuration hash, and ordered selection with `200 OK` when it is queued, running, or completed, instead
  of queueing a duplicate. A failed or cancelled match still leads to a new attempt with `202`. Concurrent
  identical requests serialize on the run row
  ([ADR-0034](docs/decisions/ADR-0034-reuse-matching-aggregation-on-creation.md)).
- Ruff now enforces blind-exception, boolean-trap, unused-argument, commented-out-code, magic-value, and
  McCabe complexity (15) rules. The ADR-0009 agreement thresholds are named once, the readiness probe reports
  only database errors as `Database unavailable`, and the review-item query, prediction batch write, XLSX
  container check, and dead-code checker were split into smaller helpers without changing behavior.
- Restored the documented local quality gates with repository-owned pre-commit/pre-push hooks, YAML
  front-matter-aware documentation validation, valid headings in maintained Markdown, and explicit Ruff
  exclusions for preserved research notebooks and upstream reference snapshots.
- Expanded GitLab CI to enforce every documented repository, static-analysis, dependency, test, coverage, and
  distribution gate. Coverage now combines fast, PostgreSQL, and Redis execution before enforcing the 80%
  project floor, while the fast suite retains a separate 70% non-regression floor.
- [`README.md`](README.md) rewritten to describe the scaffold, its architectural baseline, and the local
  development checks, replacing the legacy pipeline usage instructions.
- Paper `docs/paper/article.tex` substantially revised in response to two peer reviews: the method section
  was reorganized so classifiers sit under a shared overview; aggregation is now specified explicitly as
  normalization, voting, and certainty assignment; the case study gained per-method coverage, label
  distribution, accuracy, and agreement sections plus an analysis of errors in authority data; per-class
  recall now carries Wilson 95% confidence intervals; and a "Limitations and Reproducibility" section was
  added. The separate "Human-in-the-Loop Workflow" section was cut.
- `scripts/poster_pies.py` reworked to read final labels from the reviewed dataset instead of re-running
  ensemble voting inside the plotting script. Superseded by the scaffold reset described below.
- `.gitignore` now excludes the local `__scrap/` drafts directory and `.claude/` agent definitions.
- Snapshot creation now returns a durable pending resource instead of parsing and persisting the complete
  register inside a nominally asynchronous `202 Accepted` request. One endpoint now dispatches the declared
  supported format/packaging matrix without exposing Celery or artifact-storage details.
- `GET /api/v1/runs/{run_id}/executions` now returns the public `MethodExecutionSummary` contract, which drops
  the `queue_name` and `worker_metadata` fields previously served to every viewer. The canonical
  `MethodExecution` model retains both for internal routing and worker provenance. This restores the client
  boundary in [`docs/01-architecture.md`](docs/01-architecture.md), under which queue names and worker
  identities are never part of the public contract, and removes both fields from the generated OpenAPI
  document.
- Opaque cursors now carry an ordered tuple of sort values and validate the arity the reading endpoint
  expects, so a composite ordering can be continued without treating the position as authorization. Existing
  cursors are not portable across the change.
- Reordered the remaining implementation phases so evaluation/export and deployment hardening precede the
  Vue review client, which is now the final Phase 8 deliverable.
- Local-account sessions no longer end a fixed 8 hours after login
  ([ADR-0032](docs/decisions/ADR-0032-sliding-session-lifetime.md)). Each request slides the idle limit
  forward: 24 hours for an ordinary login with browser-session cookies, 7 days for a login with the new
  `keep_signed_in` flag, whose cookies persist. Every session ends 30 days after login. Three settings
  (`GENDERTAGGER_SESSION_IDLE_SECONDS`, `GENDERTAGGER_SESSION_KEEP_SIGNED_IN_IDLE_SECONDS`,
  `GENDERTAGGER_SESSION_MAX_LIFETIME_SECONDS`) replace `GENDERTAGGER_SESSION_TTL_SECONDS`, and migration
  `20260921_0003` adds the session kind and absolute limit; existing sessions keep their original end.
- The gateway throttles `POST /api/v1/auth/login` per client address to six attempts at once and then one
  every 12 seconds, answering with `429 rate_limited` in the API's error envelope and a `Retry-After`
  header. This bounds password guessing and the Argon2id memory each attempt costs.
- `GET /api/v1/auth/session` reports whether the session owes a password change and whether it was kept
  signed in. `POST /api/v1/me/password` now answers a wrong current password with
  `400 invalid_current_password` instead of `401 invalid_credentials`, so a `401` always means the session
  is gone.
- **Breaking:** authorization is scoped to projects
  ([ADR-0033](docs/decisions/ADR-0033-project-scoped-membership-roles.md)). Viewer, reviewer, and operator
  are now project roles held through memberships; the global `Role` schema is renamed `GlobalRole` and keeps
  only `operator`, which may create projects and becomes operator of each one it creates, and `admin`, which
  holds operator in every project. A resource in a project where the caller has no role returns `404`. Project
  responses are `AccessibleProject`, which adds the caller's `current_user_role`. `/methods` and `/classify`
  require a global role or any membership, and `users create --role` is optional. Migration `20260921_0004`
  adds `project_memberships` and deletes every global viewer and reviewer role without creating memberships,
  so non-admin users see no projects until an administrator assigns them.
- The browser client's Node pin moved from 22 to 26 (`engines` `^26.9.0`, image `node:26.9.0-alpine`, and
  `@types/node` 26), because Node 22 reaches end of life in April 2027 and Node 26 is supported until April
  2029 (decision D12 in [`docs/24-frontend-delivery-plan.md`](docs/24-frontend-delivery-plan.md)).

- Manual annotation now follows the review workbench's panel, queue-row, detail-summary,
  source-record, and collapsed-history composition across desktop and narrow layouts while retaining
  its snapshot-only filters and decisions.

### Fixed

- Evaluation-report downloads advertise the canonical Pydantic schema without reserializing immutable
  artifact bytes. Frontend report and export-manifest parsers use generated transport types and retain
  runtime shape/vocabulary checks, including optional/null fields and zero-valued evidence.
- Batch failures now share the URL-credential redaction and bounded detailed-diagnostic policy used by
  aggregation, evaluation, export, and dispatch. Redaction occurs before the 500-character limit;
  authenticated method summaries cannot retain credential-bearing URL user information from batch
  failures. Snapshot-import safe messages and anonymous classification's limited failure codes remain
  separate.
- Aggregation, evaluation, and export detail screens validate canonical resource/run/snapshot/project
  ownership before showing status, evidence, actions, or links. Rapid context changes fail closed;
  invalidated export downloads and hashing continuations cannot save or display stale bytes.
- Method and run progress refresh after every terminal batch instead of waiting for the entire method.
  Concurrent finalizers preserve committed tallies without conflicting with Prediction foreign-key
  locks; duplicate deliveries and final lifecycle semantics remain unchanged.
- Delivery plans and the frontend overview now separate implemented capabilities, local verification,
  and deferred release automation. Manual digest-based promotion remains the publication process;
  fresh-install/restore evidence is retained without claiming prior-release upgrade readiness.

- Project batches reject implementation/normalization, build/environment, frozen-configuration, and
  pinned lookup/model drift before adapter computation or Prediction persistence. Runs record exact
  installed dependency versions; canonical actual-worker receipts are captured atomically on claims and
  remain immutable. Migration `20261004_0014` preserves unknown historical provenance as null; legacy
  runs without dependency evidence require a newly accepted run. OpenAPI and frontend Run types were
  regenerated. See [ADR-0048](docs/decisions/ADR-0048-project-worker-provenance-compatibility.md).
- Direct classification caches no longer retain technical failures. Complete descriptor/resolved-config
  identity separates changed methods, models, and artifacts; successful unknowns and abstentions still
  cache, and returned mutable evidence cannot alter cached results. Recovery does not rewrite completed
  public classification jobs.
- Newly generated CSV analysis exports quote all cells and protect formula, full-width formula,
  whitespace, and control/format prefixes with an ASCII apostrophe. Canonical records, JSON, and
  previously stored artifacts remain unchanged. The supported LibreOffice Calc text-import settings,
  verified non-formula behavior, and non-lossless/non-universal spreadsheet limits are documented in
  [the export design](docs/08-ingestion-and-export.md#spreadsheet-safe-csv-analysis) and
  [ADR-0047](docs/decisions/ADR-0047-spreadsheet-safe-csv-analysis.md).
- GND implementation `gnd_v2` now gives entity type precedence over source gender: only persons
  receive male/female labels, corporate bodies remain institutions, and all other authority types
  remain substantive unknown even with explicit gender. Preserved source evidence and existing
  snapshot bytes; normalization, configuration, and historical predictions are unchanged. Added
  compiled-snapshot boundary regressions and [ADR-0046](docs/decisions/ADR-0046-gnd-entity-type-precedence.md).
- Reconciled all ten entries in the [method adapter reference](docs/20-method-adapters-reference.md)
  with their closed configurations, consumed inputs, token reductions, raw evidence, confidence,
  versions, and artifact selection. Added schema-valid configuration examples, corrected NQG's
  threshold and HF hard-label contracts, and documented the originally discovered GND discrepancy
  without changing scientific implementations or regression expectations.
- `PersonRecord.name_forms` is persisted as SQL `NULL` rather than JSON `null` when a snapshot profile
  captures no structured name forms. The JSONB column previously violated its own `name_forms_array` check
  constraint, which made every TEI-profile-v1 person insert fail.
- Restored the published parenthetical `institution` normalization and authority override in `reference_v1`,
  with paired scientific regression cases for disagreement and agreement with the pooled methods.
- Made asynchronous run dispatch recoverable across broker and coordinator failures with a transactional
  PostgreSQL outbox, a relay/reconciler process, and atomic scheduling and worker claims.
- Count every record covered by a terminal whole-batch failure in execution and run progress.
- Isolated committed PostgreSQL/Redis test state between cases so the complete service-backed suite remains
  order-independent when concurrency tests use independent sessions.
- The client read its CSRF token from a provisional `gendertagger_csrf` cookie, but the local account
  backend sets `csrf_token`, so every unsafe request from a signed-in browser would have failed with
  `403 forbidden`. The client now reads `csrf_token`.

### Removed

- The misleading `deploy/scripts/test_migration.sh` helper, which neither established a previous
  application schema nor exposed the readiness endpoint it probed. Existing-installation upgrade
  rehearsal remains an explicit operator gate in the production runbook.

- Legacy research pipeline: the classification implementation under `src/gendertagger/backend/`, and the
  analysis, plotting, and orchestration scripts in `scripts/` (including `run_all_methods.py`,
  `aggregate_results.py`, `benchmark.py`, `agreements.py`, `record_agreement.py`, `plot_kappa_heatmap.py`,
  and `poster_pies.py`).
- Generated `output/` artifacts, including per-method result CSVs, Cohen's kappa results, agreement
  summaries, and poster figures.
- `docs/QUICK_START.md` and `docs/UI_GUIDE.md`, superseded by the design documents.
- `requirements.txt` and `requirements-dev.txt`, replaced by `pyproject.toml` dependency groups and
  `uv.lock`.
- Missing-package guards left over from optional extras, which
  [ADR-0029](docs/decisions/ADR-0029-unconditional-method-dependencies.md) made core dependencies: the
  `except ImportError` blocks in six method adapters and the XLSX reader, `TabularDependencyError`, and the
  tests' `pytest.importorskip` calls. `MethodDependencyError` now covers only missing or invalid provisioned
  assets. Removing `importorskip` exposed an import-time `DeprecationWarning` from `nomquamgender`, now
  filtered narrowly in the pytest configuration.

Removed pipeline code and result artifacts remain available in version control history at commit
`36522b8`; restoring the legacy scientific fixture is a prerequisite of the implementation plan.
