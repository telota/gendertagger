# gendertagger

This repository is the architecture-first implementation of the next generation of `gendertagger`.
It captures the agreed architecture and scientific behavior of the existing Python pipeline while the
new application is built in tested phases.

The target system is a reproducible, human-in-the-loop service for semi-automated gender annotation of TEI/XML person registers.
The design preserves the published multi-method workflow while adding persistent storage, an API, task orchestration, annotation, evaluation, provenance, and deployable infrastructure.

## Architectural baseline

- **FastAPI** is the canonical public/application entry point.
- **Pydantic** is the canonical language for API, domain, configuration, task-envelope, and service contracts.
- **SQLAlchemy + PostgreSQL** provide persistence; ORM models are not the domain model.
- **Celery + Redis** provide asynchronous task execution.
- CPU, GPU, and external/slow workloads are routed to separate queues.
- Original TEI/XML and generated artifacts live behind a storage abstraction; a shared filesystem is the initial backend.
- Projects contain immutable **DatasetSnapshots**. A run always targets one immutable snapshot.
- The TEI `xml:id` is the canonical person identifier inside a project.
- Per-method predictions are immutable scientific evidence. Aggregation and human annotations never overwrite them.
- The published aggregation strategy remains the default reference strategy.
- The review/game UI is an annotation client, not a separate source of truth.
- The planned UI stack is **Vue 3 + TypeScript + Vite**, consuming `/api/v1` through OpenAPI-generated transport contracts.
- Long-running work is exposed as persisted asynchronous resources with optional SSE progress; Celery remains invisible to clients.
- Production should prefer same-origin Vue/FastAPI routing and secure HTTP-only browser sessions.

## Start here

1. Read [`AGENTS.md`](AGENTS.md).
2. Read [`docs/01-architecture.md`](docs/01-architecture.md).
3. Read [`docs/02-domain-model.md`](docs/02-domain-model.md).
4. Read [`docs/03-pydantic-contracts.md`](docs/03-pydantic-contracts.md).
5. Read [`docs/17-frontend-integration.md`](docs/17-frontend-integration.md) for the later Vue boundary.
6. Follow [`docs/15-implementation-plan.md`](docs/15-implementation-plan.md).
7. Follow [`docs/18-engineering-and-quality.md`](docs/18-engineering-and-quality.md) for local and CI checks.
8. Follow [`docs/19-coding-and-documentation-style.md`](docs/19-coding-and-documentation-style.md) for naming,
   docstrings, Markdown, and ADRs.

## Repository state

The repository is in Phase 5 method migration:

- Phase 0 repository tooling, policy checks, hooks, and CI are implemented. Clearance or removal of the
  tracked legacy research data remains a governance prerequisite for closing the phase.
- Phase 1 provides canonical contracts, all ten versioned normalization profiles, pure `reference_v1`
  aggregation, agreement/certainty assignment, and paired scientific oracles. The published parenthetical
  `institution` override is restored; mixed-category qualifier precedence still needs an explicit
  compatibility decision and regression test.
- Phase 2 provides SQLAlchemy persistence, repository/unit-of-work boundaries, Alembic migrations, lifecycle
  and provenance integrity guards, and PostgreSQL integration coverage without leaking ORM types upward.
- Phase 3 provides the authenticated `/api/v1` FastAPI vertical slice for projects, snapshots, runs, methods,
  aggregations/results, annotations, and uncertainty-first review lists, with a committed OpenAPI contract and
  typed `CurrentUser` boundary.
- Phase 4 provides Celery/Redis execution, persisted batches, transactional dispatch outboxes, reconciliation,
  atomic worker claims, retries, progress, and reconnect-safe run events.
- Phase 5 has asynchronous multi-format snapshot import, executable `reference_v1` aggregation, immutable
  lookup-asset provisioning, and registered parenthetical-qualifier, GND, gender-guesser, Wiki-Gendersort,
  HIVOTO, and nomquamgender adapters. Both transformer classifiers, the local LLM, and experimental
  HIVOTO-XGBoost remain to migrate.

- Phase 7 deployment hardening is fully implemented, shifting the application from development scripts to a hardened containerized architecture with a robust compose topology, GitLab CI publication, and operational runbooks.

Evaluation/export (Phase 6) and the Vue review client (Phase 8) remain.

## Local deployment

The local deployment uses Docker Compose and starts PostgreSQL, Redis, the FastAPI service, a CPU worker,
the current frontend placeholder, and the Nginx gateway. Install Docker with the Compose plugin, then run
the following commands from the repository root:

```bash
docker compose -f compose.yaml -f compose.dev.yaml build
docker compose -f compose.yaml -f compose.dev.yaml up -d db redis
docker compose -f compose.yaml -f compose.dev.yaml --profile ops run --rm migrate
docker compose -f compose.yaml -f compose.dev.yaml up -d api worker-cpu frontend gateway
```

The services are available at:

- API documentation: <http://localhost:8000/docs>
- API health: <http://localhost:8000/health>
- API readiness: <http://localhost:8000/ready>
- Gateway: <http://localhost:8080>
- Frontend placeholder: <http://localhost:5173>

Inspect service status and logs with:

```bash
docker compose -f compose.yaml -f compose.dev.yaml ps
docker compose -f compose.yaml -f compose.dev.yaml logs -f api worker-cpu
```

Stop the local services with:

```bash
docker compose -f compose.yaml -f compose.dev.yaml down
```

The default `down` command preserves PostgreSQL, Redis, and artifact volumes. Use `down -v` only when you
intentionally want to remove local service data.

## Provision method lookup data

GND, Wiki-Gendersort, and HIVOTO runs select compiled SQLite lookup artifacts by SHA-256, never by a mutable
filesystem path. Configure `GENDERTAGGER_DATABASE_URL` and `GENDERTAGGER_ARTIFACT_ROOT`, then provision data
before creating a run:

```bash
# HIVOTO must first be downloaded manually after accepting its RADAR license.
gendertagger assets prepare-hivoto /private/HIVOTO.csv \
  --source-version 2026-02-09 \
  --license-identifier "REPLACE_WITH_ACCEPTED_LICENSE"

# Register a checked-out Wiki-Gendersort NamesOut.txt.
gendertagger assets prepare-wiki /private/Wiki-Gendersort/NamesOut.txt \
  --source-version REPLACE_WITH_GIT_COMMIT \
  --source-url https://github.com/nicolasberube/Wiki-Gendersort

# Compile the person and corporate-body MARC21-XML files from one dated DNB release.
# Additional entity files from the same release may be passed in the same command.
gendertagger assets build-gnd \
  /private/authorities-gnd-person_dnbmarc_YYYYMMDD.mrc.xml.gz \
  /private/authorities-gnd-koerperschaft_dnbmarc_YYYYMMDD.mrc.xml.gz \
  --source-version YYYY-MM-DD \
  --source-url https://data.dnb.de/GND/
```

`fetch-wiki` accepts one explicit HTTPS URL plus `--expected-sha256`. `fetch-gnd` accepts one or more HTTPS
URLs and requires one repeated `--expected-sha256` value for each URL. Use the dated MARC21-XML person and
corporate-body files from the same [DNB GND release](https://data.dnb.de/GND/); runtime classification never
accesses the network. Every preparation command prints one JSON object. Copy its `lookup_sha256` into the
method's `config` in [`config/example.yaml`](config/example.yaml). Original source bytes and the compiled
derivative are both retained as content-addressed artifacts. See
[`ADR-0023`](docs/decisions/ADR-0023-content-addressed-sqlite-method-lookups.md) for provenance and licensing
rules.

## Development checks

Install the uv version required by `pyproject.toml` and Node.js 18 or newer, then run:

```bash
uv sync --locked
npm ci --ignore-scripts --no-audit --no-fund
uv run --locked python scripts/check_documentation.py
uv run --locked python scripts/check_contract_naming.py
uv run --locked python scripts/check_package_initializers.py
npm run typecheck:pyright
uv run --locked python scripts/check_asyncio_runner.py
uv run --locked pre-commit run --all-files
uv run --locked pytest \
  -m "not integration and not postgres and not redis and not e2e and not slow and not gpu and not external" \
  --hypothesis-profile=ci --cov --cov-fail-under=70
uv build --no-sources
uv run --locked python scripts/check_distribution.py dist/*
```

Install Git hooks after `git init` with `uv run --locked pre-commit install --install-hooks`. Full contributor
policy, service-backed test commands, and the combined 80% coverage gate are in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Scientific reference behavior

The published workflow uses the canonical labels:

- `male`
- `female`
- `unknown`
- `institution`

It distinguishes a method's substantive `unknown` result from an `abstain` status. Per-method confidences are preserved as `method_confidence` but do **not** influence the reference majority vote.

See [`docs/07-methods-and-aggregation.md`](docs/07-methods-and-aggregation.md) for the normative reference behavior.

## License

The project source is licensed under the [MIT License](LICENSE). Bundled or referenced datasets, model
artifacts, and scientific fixtures require their own compatibility and redistribution review.
