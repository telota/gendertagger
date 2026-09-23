# Contributing

`AGENTS.md`, the normative documents in `docs/`, and accepted ADRs are the sources of truth. If
they disagree, stop and resolve the specification rather than choosing whichever behavior is easiest
to implement.

## Development setup

Install [uv](https://docs.astral.sh/uv/) at the version required by `pyproject.toml` and Node.js 18 or
newer, then run:

```bash
uv sync --locked
npm ci --ignore-scripts --no-audit --no-fund
```

After the Git repository has been initialized, install the local hooks:

```bash
uv run --locked pre-commit install --install-hooks
```

The hooks format and lint changed files, validate documentation and contract naming, validate the lockfile and
repository metadata, run strict typing and import-boundary checks, and run the fast test suite before a push.
CI remains authoritative.

## Required checks

Run the same checks CI runs before opening a merge request:

```bash
uv lock --check
uv run --locked python scripts/check_documentation.py
uv run --locked python scripts/check_contract_naming.py
uv run --locked python scripts/check_package_initializers.py
uv run --locked python scripts/check_dead_code.py
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
npm audit --audit-level=high
npm run typecheck:pyright
uv run --locked lint-imports
uv audit --locked
uv run --locked python scripts/check_asyncio_runner.py
COVERAGE_FILE=.coverage.fast uv run --locked pytest \
  -m "not integration and not postgres and not redis and not e2e and not slow and not gpu and not external" \
  --hypothesis-profile=ci --cov --cov-report=term-missing \
  --cov-report=xml:coverage-fast.xml --cov-fail-under=70
GENDERTAGGER_DATABASE_URL=postgresql+psycopg://user:password@localhost/gendertagger \
  uv run --locked alembic upgrade head
GENDERTAGGER_DATABASE_URL=postgresql+psycopg://user:password@localhost/gendertagger \
  uv run --locked alembic check
GENDERTAGGER_TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost/postgres \
  COVERAGE_FILE=.coverage.postgres uv run --locked pytest \
  -m "integration and postgres" --hypothesis-profile=ci --cov \
  --cov-report=term-missing --cov-report=xml:coverage-postgres.xml --cov-fail-under=0
GENDERTAGGER_DATABASE_URL=postgresql+psycopg://user:password@localhost/gendertagger \
  GENDERTAGGER_TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost/postgres \
  GENDERTAGGER_TEST_REDIS_URL=redis://localhost:6379/15 \
  COVERAGE_FILE=.coverage.redis uv run --locked pytest -m "redis" \
  --hypothesis-profile=ci --cov --cov-report=term-missing \
  --cov-report=xml:coverage-redis.xml --cov-fail-under=0 -p no:unraisableexception
uv run --locked coverage combine \
  .coverage.fast .coverage.postgres .coverage.redis
uv run --locked coverage xml --fail-under=0 -o coverage.xml
uv run --locked coverage report --fail-under=85
uv run --locked coverage report --include=src/gendertagger/methods/normalization.py --fail-under=100
uv run --locked coverage report --include=src/gendertagger/domain/aggregation.py --fail-under=100
uv run --locked coverage report --include=src/gendertagger/domain/aggregation_assessment.py --fail-under=100
uv run --locked coverage report --include=src/gendertagger/export/tei_profile.py --fail-under=100
uv build --no-sources
uv run --locked python scripts/check_distribution.py dist/*
```

The Vue client has its own lockfile and requires the Node version in `frontend/package.json` `engines`. Its CI
jobs run:

```bash
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend run i18n:check
npm --prefix frontend run api:check
npm --prefix frontend audit --audit-level=high
npm --prefix frontend test
npm --prefix frontend run build
```

A backend contract change is two commands, and both outputs are committed with the change:

```bash
uv run --locked python scripts/update_openapi_snapshot.py   # contracts/openapi-v1.json
npm --prefix frontend run api:generate                      # frontend/src/api/schema.d.ts
```

Review the snapshot diff as a public contract change. The backend contract test fails when the first step
was skipped, and `api:check` fails when the second was.

The PostgreSQL test role must be allowed to create temporary databases. The integration suite creates a
randomly named database per migration/repository scope and removes it after the session.

Redis tests require `GENDERTAGGER_TEST_REDIS_URL` to select a dedicated nonzero database. The test fixture
purges that database before and after every Redis-marked test; never point it at a shared or production broker.

The 70% fast-suite threshold is a quick non-regression signal. It does not replace or lower the mandatory
85% project floor, which is evaluated after combining the fast, PostgreSQL, and Redis coverage data. The
combined report also requires 100% branch coverage for normalization, reference aggregation, certainty
assessment, and TEI projection. Every partial suite remains independently blocking on test failures.

Use `uv run --locked pre-commit run --all-files` to exercise all pre-commit-stage hooks manually.
Use `uv run --locked pre-commit run --all-files --hook-stage pre-push` to exercise the mypy/Pyright,
import-boundary, runner-capability, and fast-test hooks without pushing.

## Change discipline

- Keep merge requests narrow and explain contract, persistence, provenance, scientific, security,
  and deployment effects.
- Add or update tests at the layer where behavior belongs. Do not hide a failed invariant behind an
  end-to-end test alone.
- Use Pydantic models at application boundaries. Never expose SQLAlchemy models through services or
  the public API.
- Treat OpenAPI changes as public contract changes and review generated diffs deliberately.
- Include a reviewed Alembic migration with every persistence change once Phase 2 begins.
- Record model, data, configuration, prompt, and method revisions that affect reproducibility.
- Use narrowly scoped, error-code-specific `# type: ignore[...]` and `# noqa: ...` comments with a
  reason. Broad suppressions and unchecked missing imports are not accepted.
- Follow the naming, Google-style docstring, Markdown, and ADR rules in
  `docs/19-coding-and-documentation-style.md`. Public contract field renames require explicit compatibility
  review.
- Keep production `__init__.py` files docstring-only. Import symbols from their defining modules and read the
  installed version through `importlib.metadata`.
- Keep ordinary tests deterministic and offline. Live services, model downloads, GPUs, and large
  corpora belong in explicitly marked protected/scheduled jobs.

## Scientific changes

Changes to labels, normalization, aggregation, authority overrides, tie behavior, certainty tiers,
TEI output semantics, or evaluation definitions must update the relevant design document, add an
ADR, and change explicit scientific regression expectations in the same merge request. Never update
golden outputs merely to make a failing test pass.

Keep two distinct regression oracles:

- `legacy_characterization` records what the old pipeline actually did;
- `reference_v1` records the approved normative behavior.

Any difference between them must be intentional and documented.

## Data and generated files

Only synthetic or explicitly cleared, licensed fixtures may enter Git. Never commit source editorial
data, databases, model weights, secrets, runtime artifacts, or anything under `__scrap/`. Raw source
fixtures whose byte hash is tested belong under `tests/fixtures/raw/`; expected scientific outputs
must not be regenerated during an ordinary test run.

See `docs/18-engineering-and-quality.md` for the full engineering policy and
`docs/19-coding-and-documentation-style.md` for naming and documentation conventions.
