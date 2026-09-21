# Engineering and quality policy

## Purpose

Engineering controls protect both software behavior and the published scientific semantics. CI begins
with repository initialization and gains gates as each architectural phase lands. Deployment automation
does not precede a deployable, tested vertical slice.

## Reproducible toolchain

- Hatchling builds the Python distribution.
- uv resolves and installs dependencies. Commit `uv.lock`; CI uses only locked installs.
- npm installs the official Pyright CLI from the committed root `package-lock.json`; Node.js is a development
  runtime and does not enter the Python package metadata.
- The Vue client has its own `frontend/package.json` and `frontend/package-lock.json`. Its `.npmrc` sets
  `engine-strict=true`, so `npm ci` in `frontend/` needs the Node version in its `engines` field.
- Direct development tools are pinned in `pyproject.toml`; the lockfile records the complete transitive
  Python environment. JavaScript development tools are pinned exactly in `package.json`.
- Runtime libraries belong in `[project.dependencies]`. Heavy method/model dependencies should use
  deliberate optional groups and must not enter ordinary CI accidentally.
- CI exercises the minimum supported Python. The checked-in `.python-version` selects that interpreter for
  local development; `requires-python` in `pyproject.toml` remains the authoritative compatibility
  declaration.

The canonical commands are listed in `CONTRIBUTING.md`. CI is the final arbiter; local hooks are a fast
feedback mechanism.

## Python standards

- Ruff owns formatting, import sorting, and linting. Do not hand-format around it.
- Ruff enforces Python naming, built-in shadowing, and Google-style public docstrings. Repository-specific
  Pydantic/config field vocabulary is checked by `scripts/check_contract_naming.py`.
- Ruff also rejects blind `except Exception` handlers, boolean positional parameters, unused arguments,
  commented-out code, unnamed numeric literals in comparisons, and functions above McCabe complexity 15.
  Name thresholds that carry scientific meaning once, next to the ADR that defines them. A handler that turns
  arbitrary adapter or broker failures into an `error` result may stay broad with a reasoned suppression.
  Lower the complexity limit toward 10 as code is refactored rather than raising it.
- Regular production packages use explicit, docstring-only initializers. The package-initializer policy rejects
  re-exports, assignments, runtime setup, and accidental namespace packages.
- Strict mypy applies to `src/`, `tests/`, and `scripts/`. Public contracts, service boundaries,
  repositories, and adapters must be fully typed. Confine `Any` to inspected raw external payloads.
- Pyright runs as a complementary required analysis over `src/`, `tests/`, and `scripts`, using the checked-in
  configuration that Pylance also understands. Pylance itself remains an editor integration rather than a
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
- `e2e`: a full supported workflow over a tiny fixture;
- `slow`, `gpu`, and `external`: excluded from ordinary CI and enabled only explicitly.

Every test must be independent of execution order and shared mutable state. PostgreSQL-specific behavior is
tested on PostgreSQL, and at least one Celery path uses a real Redis broker/worker rather than eager mode.

The overall coverage floor is 85%, enforced in `pyproject.toml` and `.gitlab-ci.yml`. Ratcheting it further
is an operational decision once real coverage headroom is measured, not tied to a specific phase. CI records
separate data from the fast, PostgreSQL, and Redis suites, then combines those data before enforcing the
project floor. The fast suite
also has a 70% non-regression floor so unit and contract coverage cannot silently collapse behind integration
coverage. A zero threshold on a service-specific partial run only defers percentage evaluation; test failures
remain blocking. Normative normalization, reference aggregation, certainty assessment, and TEI-projection
modules have individual 100% branch-coverage gates. Coverage is a gap detector, not a substitute for
decision-table and property-based tests.

## CI and delivery

The initial GitLab pipeline performs:

1. lockfile validation;
2. documentation structure/link/manifest/ADR validation, semantic contract naming, and package-initializer
   checks;
3. Ruff, strict mypy, complementary Pyright, and import-boundary checks;
4. locked Python and npm dependency vulnerability audits;
5. the fast, PostgreSQL, and Redis pytest suites with combined branch coverage;
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
every reference adapter, and the complete evaluation/export workflow, plus the packaging, SBOM, and
secret-detection gates from Phase 7's operational hardening, and the Phase 8 frontend jobs listed in
`14-testing.md`; heavy-model checks remain on protected or scheduled runners.

Ordinary merge-request jobs have no production secrets and must not use private-network, GPU, model, or
deployment runners. Such runners are protected and accept only trusted protected refs or schedules.

Tagged releases should build immutable artifacts once, publish checksums/SBOM/provenance, and promote those
same artifacts with manual production approval. Database deployment requires a migration rehearsal and a
verified backup/restore policy. Ordinary branches never deploy production.

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

`scripts/check_documentation.py` scans only maintained documentation roots, so ignored migration material and
tool caches are never traversed. It validates local links offline; external-link availability is intentionally
not a merge-request gate. `scripts/check_contract_naming.py` is restricted to annotated canonical/config model
fields, leaving ordinary local naming to Ruff and review.
`scripts/check_package_initializers.py` keeps imports and behavior in defining modules rather than hiding them
behind package import side effects. `scripts/check_dead_code.py` prevents orphan symbols and dead code from
accumulating in `src/gendertagger`.

