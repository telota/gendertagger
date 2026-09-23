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

Access to data is per project ([ADR-0033](docs/decisions/ADR-0033-project-scoped-membership-roles.md)). An
`admin` sees every project; a global `operator` may create projects and becomes operator of each one it
creates. Everyone else needs no global role, only a project membership granted by an administrator:

```bash
docker compose -f compose.yaml -f compose.dev.yaml run --rm api \
  gendertagger users create --username reviewer --display-name "Reviewer"
docker compose -f compose.yaml -f compose.dev.yaml run --rm api \
  gendertagger projects add-member --project my-edition --username reviewer --role reviewer
```

Project roles are `viewer`, `reviewer`, and `operator`; `projects list-members` and `projects remove-member`
complete the set.

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
[`config/example.yaml`](backend/config/example.yaml). Original source bytes and the compiled derivative are both
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

### 5. Seed representative frontend data

After migrations, the development stack can be populated with two synthetic projects and the full set of
browser-visible lifecycle and review states. The command creates `frontend-viewer`, `frontend-reviewer`,
and `frontend-operator`, all with the printed development-only password. It also creates ready and failed
snapshots; running, completed, and failed runs; completed and failed method executions; every agreement and
certainty tier; annotation history and a reproducible stale-revision conflict; and completed evaluation and
JSON-export artifacts.

The safety flag is mandatory. The marker project makes an exact repeat a read-only no-op. Mounting the
backend project read-only supplies the development script and shared production-path seed helpers without adding
them to the runtime image:

```bash
docker compose -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd)/backend:/workspace:ro" -w /workspace api \
  python -m scripts.seed_frontend_development --confirm-development-database
```

Pass `--password` to replace the default `development-only` credential. The command emits a JSON manifest
containing the account and resource identifiers that browser tests need. It is intentionally a repository
development tool, not a production administration command.

Stop the local services with:

```bash
docker compose -f compose.yaml -f compose.dev.yaml down
```

The default `down` command preserves PostgreSQL, Redis, and artifact volumes. Use `down -v` only when you
intentionally want to remove local service data.

## Documentation

- Current status: [`PLAN.md`](PLAN.md)
- Product and architecture: [`SPEC.md`](SPEC.md) and
  [`docs/01-architecture.md`](docs/01-architecture.md)
- Phase roadmap and deferred scope: [`docs/15-implementation-plan.md`](docs/15-implementation-plan.md) and
  [`docs/22-future-development.md`](docs/22-future-development.md)
- Scientific behavior: [`docs/07-methods-and-aggregation.md`](docs/07-methods-and-aggregation.md)
- Contributor setup and quality gates: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Coding-agent instructions: [`AGENTS.md`](AGENTS.md)
- Complete design-document index: [`docs/00-design-index.md`](docs/00-design-index.md)

## License

The project source is licensed under the [MIT License](LICENSE). Bundled or referenced datasets, model
artifacts, and scientific fixtures require their own compatibility and redistribution review.
