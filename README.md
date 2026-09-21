# gendertagger

This repository is the implementation of the next generation of `gendertagger`.

The target system is a reproducible, human-in-the-loop service for semi-automated gender annotation of TEI/XML person registers.
The design preserves the published multi-method workflow while adding persistent storage, an API, task orchestration, annotation, evaluation, provenance, and deployable infrastructure.

## Quickstart

The stack runs on Docker Compose. Install Docker with the Compose plugin, then run these commands from the
repository root.

### 1. Build and start core services

```bash
docker compose -f compose.yaml -f compose.dev.yaml build
docker compose -f compose.yaml -f compose.dev.yaml up -d db redis
docker compose -f compose.yaml -f compose.dev.yaml --profile ops run --rm migrate
```

### 2. Create a login account

Every `/api/v1` endpoint requires a session, and accounts are created only by an administrator from the CLI
([ADR-0031](docs/decisions/ADR-0031-local-database-authentication.md)):

```bash
docker compose -f compose.yaml -f compose.dev.yaml run --rm api \
  gendertagger users create --username admin --display-name "Admin" --role admin
```

Omit `--password` to have one generated; the command prints it once in its JSON output. A new account must
change its password before any other endpoint accepts it: sign in with `POST /api/v1/auth/login`, then call
`POST /api/v1/me/password`. `gendertagger users reset-password --user-id <uuid>` forces a new password later
and signs the account out everywhere.

### 3. Provision method data

Several reference methods classify from a compiled, content-addressed data artifact rather than at request
time, so they need one-time provisioning before a run can use them:

| Method | Data source | CLI subcommand |
|---|---|---|
| `gnd` | Dated DNB GND MARC21-XML release | `assets build-gnd` / `assets fetch-gnd` |
| `wiki_gendersort` | Wiki-Gendersort `NamesOut.txt` | `assets prepare-wiki` / `assets fetch-wiki` |
| `hivoto` | HIVOTO source table (manual download, RADAR license) | `assets prepare-hivoto` |
| `hf_distilbert`, `hf_genderize` | Locally materialized Hugging Face model directory | `assets prepare-hf-model` |
| `hivoto_xgboost` (experimental) | Trained XGBoost bundle, reuses a registered `hivoto_lookup` | `assets prepare-hivoto-xgboost` |
| `parenthetical_qualifier`, `gender_guesser`, `nomquamgender` | none | — |
| `local_llm` | An OpenAI-compatible endpoint via `LLM_BASE_URL` (no compiled artifact) | — |

Run the `assets` CLI inside a one-off container from the already-built `api` image so it shares the
container's `GENDERTAGGER_DATABASE_URL` and its default `GENDERTAGGER_ARTIFACT_ROOT`
(`/app/data/artifacts`), which is the same named volume the running `api` and `worker-cpu` services read
from. Running the CLI on the bare host instead would write artifacts nothing else can see. Bind-mount the
host directory holding your private, licensed source files read-only into the container:

```bash
# HIVOTO must first be downloaded manually after accepting its RADAR license.
docker compose -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd)/private:/private:ro" api \
  gendertagger assets prepare-hivoto /private/HIVOTO.csv \
  --source-version 2026-02-09 \
  --license-identifier "REPLACE_WITH_ACCEPTED_LICENSE"

# Register a checked-out Wiki-Gendersort NamesOut.txt.
docker compose -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd)/private:/private:ro" api \
  gendertagger assets prepare-wiki /private/Wiki-Gendersort/NamesOut.txt \
  --source-version REPLACE_WITH_GIT_COMMIT \
  --source-url https://github.com/nicolasberube/Wiki-Gendersort

# Compile the person and corporate-body MARC21-XML files from one dated DNB release.
# Additional entity files from the same release may be passed in the same command.
docker compose -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd)/private:/private:ro" api \
  gendertagger assets build-gnd \
  /private/authorities-gnd-person_dnbmarc_YYYYMMDD.mrc.xml.gz \
  /private/authorities-gnd-koerperschaft_dnbmarc_YYYYMMDD.mrc.xml.gz \
  --source-version YYYY-MM-DD \
  --source-url https://data.dnb.de/GND/

# Register a locally materialized Hugging Face model directory (downloaded separately, once,
# outside this workflow; runtime classification never accesses the network).
docker compose -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd)/private:/private:ro" api \
  gendertagger assets prepare-hf-model /private/models/padmajabfrl-gender-classification \
  --method-name hf_distilbert \
  --source-identifier padmajabfrl/Gender-Classification \
  --source-revision REPLACE_WITH_PINNED_COMMIT_SHA
```

`fetch-wiki` accepts one explicit HTTPS URL plus `--expected-sha256`. `fetch-gnd` accepts one or more HTTPS
URLs and requires one repeated `--expected-sha256` value for each URL. Use the dated MARC21-XML person and
corporate-body files from the same [DNB GND release](https://data.dnb.de/GND/). `prepare-hivoto-xgboost`
follows the same pattern as `prepare-hf-model` but additionally requires `--hivoto-lookup-sha256` naming an
already-registered `hivoto_lookup` artifact; run `gendertagger assets prepare-hivoto-xgboost --help` inside
the container for its full argument list.

Every preparation command prints one JSON object. Copy its `lookup_sha256` into the method's `config` in
[`config/example.yaml`](config/example.yaml). Original source bytes and the compiled derivative are both
retained as content-addressed artifacts. See
[`ADR-0023`](docs/decisions/ADR-0023-content-addressed-sqlite-method-lookups.md) for provenance and
licensing rules.

### 4. Start the remaining services

```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d api worker-cpu frontend gateway
```

The services are available at:

- API documentation: <http://localhost:8000/docs>
- API health: <http://localhost:8000/health>
- API readiness: <http://localhost:8000/ready>
- Gateway: <http://localhost:8080>
- Frontend (static build): <http://localhost:5173>

For hot reload while working on the client, run `npm run dev` in `frontend/` on the host instead; it proxies
`/api/v1` to `http://localhost:8000`. See [`frontend/README.md`](frontend/README.md).

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
- The UI stack is **Vue 3 + TypeScript + Vite** in [`frontend/`](frontend/), consuming `/api/v1` through OpenAPI-generated transport contracts.
- Long-running work is exposed as persisted asynchronous resources with optional SSE progress; Celery remains invisible to clients.
- Production should prefer same-origin Vue/FastAPI routing and secure HTTP-only browser sessions.

## Start here

1. Read [`AGENTS.md`](AGENTS.md).
2. Read [`docs/01-architecture.md`](docs/01-architecture.md).
3. Read [`docs/02-domain-model.md`](docs/02-domain-model.md).
4. Read [`docs/03-pydantic-contracts.md`](docs/03-pydantic-contracts.md).
5. Read [`docs/17-frontend-integration.md`](docs/17-frontend-integration.md) for the Vue client boundary.
6. Follow [`docs/15-implementation-plan.md`](docs/15-implementation-plan.md).
7. Follow [`docs/18-engineering-and-quality.md`](docs/18-engineering-and-quality.md) for local and CI checks.
8. Follow [`docs/19-coding-and-documentation-style.md`](docs/19-coding-and-documentation-style.md) for naming,
   docstrings, Markdown, and ADRs.

## Repository state

Phases 0 through 7 are complete:

- Phase 0 repository tooling, policy checks, hooks, and CI are implemented.
- Phase 1 provides canonical contracts, all ten versioned normalization profiles, pure `reference_v1`
  aggregation, agreement/certainty assignment, and paired scientific oracles. The published parenthetical
  `institution` override is restored.
- Phase 2 provides SQLAlchemy persistence, repository/unit-of-work boundaries, Alembic migrations, lifecycle
  and provenance integrity guards, and PostgreSQL integration coverage without leaking ORM types upward.
- Phase 3 provides the authenticated `/api/v1` FastAPI vertical slice for projects, snapshots, runs, methods,
  aggregations/results, annotations, and uncertainty-first review lists, with a committed OpenAPI contract and
  typed `CurrentUser` boundary.
- Phase 4 provides Celery/Redis execution, persisted batches, transactional dispatch outboxes, reconciliation,
  atomic worker claims, retries, progress, and reconnect-safe run events.
- Phase 5 has asynchronous multi-format snapshot import, executable `reference_v1` aggregation, immutable
  lookup-asset provisioning, and all nine reference adapters registered (parenthetical-qualifier, GND,
  gender-guesser, Wiki-Gendersort, HIVOTO, nomquamgender, both Hugging Face transformer classifiers, and the
  local LLM), plus the experimental HIVOTO-XGBoost adapter.
- Phase 6 provides the GND benchmark evaluation, Cohen's kappa and coverage/accuracy metrics, and the TEI,
  JSON, and CSV export profiles with provenance manifests.
- Phase 7 deployment hardening is fully implemented, shifting the application from development scripts to a hardened containerized architecture with a robust compose topology, GitLab CI publication, and operational runbooks.

The Vue review client (Phase 8) is the active work; its backend prerequisites are already met. So far:

- the client scaffold in [`frontend/`](frontend/) with its OpenAPI-generated transport, German/English
  message catalogues, theme tokens, accessibility checks, and CI jobs (milestone M1);
- the local account authentication backend, with CLI provisioning and login, logout, and password-change
  endpoints ([ADR-0031](docs/decisions/ADR-0031-local-database-authentication.md)).

The application shell and every screen remain. Their sequencing, open decisions, and missing read endpoints
are in [`docs/24-frontend-delivery-plan.md`](docs/24-frontend-delivery-plan.md). See
[`docs/15-implementation-plan.md`](docs/15-implementation-plan.md) for the authoritative phase plan and
[`docs/22-future-development.md`](docs/22-future-development.md) for deferred, unimplemented candidates.

## Development checks

Install the uv version required by `pyproject.toml` and Node.js 18 or newer, then run:

```bash
uv sync --locked
npm ci --ignore-scripts --no-audit --no-fund
uv run --locked python scripts/check_documentation.py
uv run --locked python scripts/check_contract_naming.py
uv run --locked python scripts/check_package_initializers.py
uv run --locked python scripts/check_dead_code.py
npm run typecheck:pyright
uv run --locked python scripts/check_asyncio_runner.py
uv run --locked pre-commit run --all-files
uv run --locked pytest \
  -m "not integration and not postgres and not redis and not e2e and not slow and not gpu and not external" \
  --hypothesis-profile=ci --cov --cov-fail-under=70
uv build --no-sources
uv run --locked python scripts/check_distribution.py dist/*
```

The Vue client has its own lockfile and needs the Node version in `frontend/package.json` `engines`, which
`frontend/.npmrc` enforces:

```bash
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend run check   # type check, message catalogues, transport drift, tests
npm --prefix frontend run build
```

Install Git hooks after `git init` with `uv run --locked pre-commit install --install-hooks`. Full contributor
policy, service-backed test commands, and the combined 85% coverage gate are in
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
