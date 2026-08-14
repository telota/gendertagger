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

Phases 1 through 3 are complete:

- Phase 1 establishes canonical contracts, typed method adapters, all ten versioned normalization profiles,
  pure `reference_v1` aggregation, agreement/certainty assignment, and two approved scientific oracles.
- Phase 2 provides SQLAlchemy persistence, repository/unit-of-work boundaries, Alembic migrations, and
  PostgreSQL integration coverage without leaking ORM types into application services.
- Phase 3 provides the authenticated `/api/v1` FastAPI vertical slice for projects, immutable snapshot
  imports, runs, methods, aggregations/results, annotations, and filtered review lists, with a committed
  OpenAPI contract and typed `CurrentUser` boundary.

Celery execution, production method migration, evaluation/export, and the Vue client remain later phases.

## Development checks

Install the uv version required by `pyproject.toml` and Node.js 18 or newer, then run:

```bash
uv sync --locked --extra guesser --extra wiki
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
