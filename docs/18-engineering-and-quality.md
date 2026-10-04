# Engineering and quality policy

## Purpose

Engineering controls protect both software behavior and the published scientific semantics. CI begins
with repository initialization and gains gates as each architectural phase lands. Deployment automation
does not precede a deployable, tested vertical slice.

## Reproducible toolchain

- Hatchling builds the Python distribution.
- uv resolves and installs dependencies. Commit `uv.lock`; CI uses only locked installs.
- npm installs the official Pyright CLI from the committed `backend/package-lock.json`; Node.js is a development
  runtime and does not enter the Python package metadata.
- The Vue client has its own `frontend/package.json` and `frontend/package-lock.json`. Its `.npmrc` sets
  `engine-strict=true`, so `npm ci` in `frontend/` needs the Node version in its `engines` field.
- Direct development tools are pinned in `pyproject.toml`; the lockfile records the complete transitive
  Python environment. JavaScript development tools are pinned exactly in `package.json`.
- Runtime libraries belong in `[project.dependencies]`, including the method libraries required by
  [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md). Ordinary test environments install
  those locked libraries; model downloads, external inference and GPU execution remain explicitly protected.
- CI exercises the minimum supported Python. The checked-in `.python-version` selects that interpreter for
  local development; `requires-python` in `pyproject.toml` remains the authoritative compatibility
  declaration.

The canonical commands are listed in `CONTRIBUTING.md`. CI is the final arbiter; local hooks are a fast
feedback mechanism.

## Python standards

- Ruff owns formatting, import sorting, and linting. Do not hand-format around it.
- Ruff enforces Python naming, built-in shadowing, and Google-style public docstrings. Repository-specific
  Pydantic/config field vocabulary is checked by `backend/scripts/check_contract_naming.py`.
- Ruff also rejects blind `except Exception` handlers, boolean positional parameters, unused arguments,
  commented-out code, unnamed numeric literals in comparisons, and functions above McCabe complexity 15.
  Name thresholds that carry scientific meaning once, next to the ADR that defines them. A handler that turns
  arbitrary adapter or broker failures into an `error` result may stay broad with a reasoned suppression.
  Lower the complexity limit toward 10 as code is refactored rather than raising it.
- Regular production packages use explicit, docstring-only initializers. The package-initializer policy rejects
  re-exports, assignments, runtime setup, and accidental namespace packages.
- Strict mypy applies to the backend's `src/`, `tests/`, and `scripts/`. Public contracts, service boundaries,
  repositories, and adapters must be fully typed. Confine `Any` to inspected raw external payloads.
- Pyright runs as a complementary required analysis over the same backend `src/`, `tests/`, and `scripts/`,
  using the checked-in configuration that Pylance also understands. Pylance itself remains an editor integration rather than a
  headless CI dependency. The CI environment provides all classification method dependencies so all imports
  are resolved rather than hidden by missing-import suppressions.
- Suppressions must name the exact rule/error code and explain why the exception is safe.
- Scientific functions should be pure and deterministic. Inject clocks, ID generators, randomness,
  network clients, and persistence rather than reading global state inside domain logic.
- Pydantic v2 models are canonical contracts. Boundary/config/task models should reject unknown fields
  unless an explicitly versioned extension point requires otherwise.
- Use timezone-aware UTC timestamps and explicit UUID types. Never use `null` as a synonym for the
  substantive `unknown` label.

Import Linter enforces the initial package boundaries:

- canonical models do not depend on domain, entry-point, or infrastructure packages;
- domain logic does not depend on API, CLI, persistence, storage, tasks, or application services;
- services do not depend on API, CLI, or Celery entry points;
- Celery tasks do not depend on the FastAPI layer.

Extend these contracts when a new architectural package is introduced. Do not bypass a contract with a
late import or dynamic import.

## Boundary-specific rules

- FastAPI routes remain thin, use explicit request/response models, and call application services.
- SQLAlchemy models remain persistence-only. Services own transactions; repositories do not commit
  independently.
- Celery tasks use small, versioned, JSON-compatible Pydantic envelopes and call application services
  directly. At-least-once delivery must not overwrite immutable scientific results.
- TEI parsing disables external entity resolution, DTD/network loading, recovery, and unrestricted huge
  trees. Tests cover hostile as well as valid XML. Original bytes are hashed before parsing and are never
  mutated in place.
- Package and tabular readers treat ZIP, TAR.GZ, and XLSX as untrusted containers. Tests cover path and name
  ambiguity, special members, nested or encrypted content, decompression limits, workbook active content,
  formulas, external links, and spreadsheet type coercion as well as valid imports.
- Multi-source imports have deterministic member order, collection-wide identity checks, immutable manifests,
  and record-level member/locator provenance. Parser and persistence tests cover every supported
  format/packaging/profile combination.
- Logs use identifiers and sanitized diagnostics; source content, secrets, and raw model responses are not
  emitted indiscriminately.

The detailed requirements remain in `01-architecture.md`, `03-pydantic-contracts.md`,
`06-task-queue.md`, `08-ingestion-and-export.md`, and `13-auth-and-security.md`.
Naming and documentation rules are defined in `19-coding-and-documentation-style.md`.

## Test suites

Markers define execution requirements rather than importance:

- `unit`, `contract`, and `scientific`: deterministic, offline merge-request tests;
- `integration`, `postgres`, and `redis`: service-backed tests introduced with their phases;
- `postgres_rollback`: individually audited `db_session` cases that require proven outer rollback;
- `e2e`: a full supported workflow over a tiny fixture;
- `slow`, `gpu`, and `external`: excluded from ordinary CI and enabled only explicitly.

The canonical profile runner in `backend/scripts/run_tests.py` generates the marker expressions for local,
push, and CI runs. Collection validates that every ordinary test belongs to exactly one profile:
infrastructure-free cases are Core (`core`), PostgreSQL-only cases are PostgreSQL (`postgres`), and Redis
cases are Redis (`redis`) even when they also require PostgreSQL. Explicit protected markers exclude a
case from ordinary profiles. Missing
infrastructure assignment is a collection error; no ordinary test may silently fall outside every suite.

Every test must be independent of execution order and shared mutable state. PostgreSQL-specific behavior is
tested on PostgreSQL, and at least one Celery path uses a real Redis broker/worker rather than eager mode.

PostgreSQL committed cleanup remains the default. The `postgres_rollback` opt-in requires a reviewed test
that uses only the supplied SQLAlchemy session. Collection rejects inherited or incompatible opt-ins;
teardown skips truncation only after confirmed rollback with no observed transaction escape across function
fixture setup, execution, and teardown. Failure to prove isolation retains truncation and fails the test.
Direct DBAPI calls and textual transaction-control statements require the default cleanup.

The overall coverage floor is 85%, enforced in `pyproject.toml` and `.gitlab-ci.yml`. Ratcheting it further
is an operational decision once real coverage headroom is measured, not tied to a specific phase. CI records
separate data from the Core, PostgreSQL, and Redis profiles, then combines those data before enforcing the
Backend project floor. The Core profile
also has a 70% non-regression floor so unit and contract coverage cannot silently collapse behind integration
coverage. A zero threshold on a service-specific partial run only defers percentage evaluation; test failures
remain blocking. Normative normalization, reference aggregation, certainty assessment, and TEI-projection
modules have individual 100% branch-coverage gates. Coverage is a gap detector, not a substitute for
decision-table and property-based tests.

## CI and delivery

The initial GitLab pipeline performs:

1. lockfile validation;
2. documentation structure/link/index/ADR validation, semantic contract naming, and package-initializer
   checks;
3. Ruff, strict mypy, complementary Pyright, and import-boundary checks;
4. locked Python and npm dependency vulnerability audits;
5. the Core, PostgreSQL, and Redis pytest profiles with combined Backend branch coverage;
6. wheel and source-distribution construction plus a sensitive-content policy check;
7. GitLab SAST and secret detection;
8. frontend lint, formatting, type checking, message-catalogue and transport-drift checks, npm audit, Vitest
   with its coverage floor, and the production build.

The base CI image is pinned by version and multi-platform manifest digest. Review and update both together;
do not replace the digest with a mutable convenience tag.

GitLab-managed security templates track the installed GitLab release and can change when the instance is
upgraded. Review their jobs after upgrades. Scanner reports become merge-blocking only when the GitLab project
has an applicable security approval policy; the included templates alone primarily produce reports.

Before TestClient-based tests, CI runs a bounded cross-thread asyncio wake-up probe. Starlette's TestClient
needs local socket-pair communication to wake its background event loop; a restricted or broken runner must
fail with a direct diagnostic instead of consuming the entire test-job timeout.

The merge-request pipeline covers PostgreSQL/Alembic, API/OpenAPI, Redis/Celery, conformance coverage for
every reference adapter, and the complete evaluation/export workflow, plus packaging, secret detection,
and the frontend jobs described above. Image publishing and image SBOM generation run only on the
default branch; heavy-model checks remain on protected or scheduled runners.

Local push checks use `backend/scripts/check_project.py` to select affected components from all pushed paths.
Documentation validation always runs. Backend contract inputs, deployment/configuration shared by both
clients, verification tooling, and unknown paths conservatively select both components; an empty path set
also selects both. This feedback optimization does not reduce required full handoff checks or make CI jobs
conditional. Until exact-input reuse is separately specified, every selected check executes afresh.

Repository-policy scripts run on the pinned Python interpreter without installing application dependencies.
Package construction uses isolated build tooling, and combined coverage installs only the locked test-tool
group. Tests and type analysis keep the complete locked application environment. CI publishes JUnit timing
reports for each backend profile and the frontend alongside coverage artifacts. Coverage combination keeps
all three suite artifacts from the same pipeline and preserves every threshold.

Package-manager caches are scoped to the pinned image/tool family and both project manifests and lockfiles.
Only the backend and frontend quality jobs upload their respective caches; other consumers only pull, and
the standard-library repository-policy job does not transfer a package cache. Installed virtual environments
and `node_modules` are not shared as artifacts. Frontend tests depend on frontend validation/audit, frontend
builds depend on those tests, and Python distribution checks depend on lockfile and repository policy.
Those dependencies suppress unrelated artifact downloads and allow component feedback sooner. All other
quality and coverage jobs remain mandatory, and image publishing retains the full stage barrier.

Ordinary merge-request jobs have no production secrets and must not use private-network, GPU, model, or
deployment runners. Such runners are protected and accept only trusted protected refs or schedules.

Default-branch CI builds each application image once and publishes both a full commit-SHA tag and the
moving branch-slug alias (`main` for the current default branch). The SBOM jobs scan the exact image
digests recorded by those builds. Production promotion is manual: select both images from one successful
pipeline using its full SHA, retain the digest references and SBOMs, and follow the
[production runbook](21-production-promotion.md). Commit-SHA tagging alone does not enforce registry
immutability; digests identify the exact artifacts. CI does not publish version tags or deploy any environment.

Versioned release automation remains deferred. The publication scope uses the manual runbook above;
future tagged releases should promote the already-tested artifacts with checksums/SBOM/provenance and
manual production approval. For an existing installation, database deployment requires rehearsal
against its actual previous schema/data, including startup, restore, and rollback. A fresh-install
check is not upgrade evidence; retain the runbook's installation-specific verification record.
Ordinary branches never deploy production.

## Repository controls

After repository initialization, configure GitLab to protect `main`, require successful pipelines and review,
and prevent direct pushes. Add `CODEOWNERS` entries once the actual GitLab user/group handles are known for:

- `.gitlab-ci.yml` and `.gitlab/`;
- `uv.lock` and dependency metadata;
- migrations and persistence models;
- authentication/security code;
- normative scientific modules, fixtures, design documents, and ADRs.

The repository cannot encode those GitLab permissions by itself; they are part of project setup and should be
verified before accepting implementation merge requests.

`backend/scripts/check_documentation.py` scans only maintained documentation roots, so ignored migration material and
tool caches are never traversed. It validates local links offline; external-link availability is intentionally
not a merge-request gate. `backend/scripts/check_contract_naming.py` is restricted to annotated canonical/config model
fields, leaving ordinary local naming to Ruff and review.
`backend/scripts/check_package_initializers.py` keeps imports and behavior in defining modules rather than hiding them
behind package import side effects. `backend/scripts/check_dead_code.py` checks declaration,
reference, and protocol heuristics in `backend/src/gendertagger`; it is not proof of production reachability.

The frontend's `npm run unused:check` uses pinned Knip with one production root, `src/main.ts`, and
Vue-template/lazy-import edges. Tests and tooling are not application roots. Only unused exports/types
in generated `src/api/schema.d.ts` are exempt; file reachability and unresolved imports still apply.
The check runs through local `npm run check`, GitLab validation, and pre-commit. Its precise scope and
fixtures are documented in [the frontend coding guidelines](26-frontend-coding-guidelines.md#production-unused-code-gate).
