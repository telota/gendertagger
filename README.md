# gendertagger

This is a human-in-the-loop tool for semi-automated gender annotation of TEI/XML person registers of digital scholarly editions.

## Setup

Follow [QUICKSTART.md](QUICKSTART.md) to install a local instance or a shared server with Docker
Compose, initialize the database, and create the first administrator. For contributor tooling and
checks, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Method data

After setup, keep `COMPOSE_FILE` set to the local or server mode chosen in the quickstart. The
commands below use that mode and its shared database and artifact storage.

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
| `local_llm` | An OpenAI-compatible endpoint and model in the method configuration (no compiled artifact) | — |

Run the `assets` CLI inside a one-off container from the already-built `api` image so it shares the
container's `GENDERTAGGER_DATABASE_URL` and its default `GENDERTAGGER_ARTIFACT_ROOT`
(`/app/data/artifacts`), which is the same named volume the running `api` and `worker-cpu` services read
from. Running the CLI on the bare host instead would write artifacts nothing else can see. Bind-mount the
host directory holding your private, licensed source files read-only into the container:

```bash
# HIVOTO must first be downloaded manually after accepting its RADAR license.
docker compose run --rm \
  -v "$(pwd)/private:/private:ro" api \
  gendertagger assets prepare-hivoto /private/HIVOTO.csv \
  --source-version 2026-02-09 \
  --license-identifier "REPLACE_WITH_ACCEPTED_LICENSE"

# Register a checked-out Wiki-Gendersort NamesOut.txt.
docker compose run --rm \
  -v "$(pwd)/private:/private:ro" api \
  gendertagger assets prepare-wiki /private/Wiki-Gendersort/NamesOut.txt \
  --source-version REPLACE_WITH_GIT_COMMIT \
  --source-url https://github.com/nicolasberube/Wiki-Gendersort

# Compile the person and corporate-body MARC21-XML files from one dated DNB release.
# Additional entity files from the same release may be passed in the same command.
docker compose run --rm \
  -v "$(pwd)/private:/private:ro" api \
  gendertagger assets build-gnd \
  /private/authorities-gnd-person_dnbmarc_YYYYMMDD.mrc.xml.gz \
  /private/authorities-gnd-koerperschaft_dnbmarc_YYYYMMDD.mrc.xml.gz \
  --source-version YYYY-MM-DD \
  --source-url https://data.dnb.de/GND/

# Register a locally materialized Hugging Face model directory (downloaded separately, once,
# outside this workflow; runtime classification never accesses the network).
docker compose run --rm \
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

Every preparation command prints one JSON object. Copy its `lookup_sha256` into the corresponding method's
`config` in the JSON request body for `POST /api/v1/runs`. The canonical request example is published in the
OpenAPI documentation at <http://localhost:8000/docs> in local mode and in
[`contracts/openapi-v1.json`](contracts/openapi-v1.json). Original source bytes and the compiled derivative are
both retained as content-addressed artifacts. See
[`ADR-0023`](docs/decisions/ADR-0023-content-addressed-sqlite-method-lookups.md) for provenance and
licensing rules.

## Frontend development

The local Compose mode in [QUICKSTART.md](QUICKSTART.md) runs Vite with hot reload by default.
Open <http://localhost:8080>, edit files in `frontend/`, and save; no image rebuild or host Node
installation is needed for source changes. The API also reloads source edits; workers still need
an explicit restart. See the [development workflow](QUICKSTART.md#development-workflow) for dependency
updates and the [frontend guide](frontend/README.md#local-development) for optional host-side Vite.

### Seed representative frontend data

After migrations, the development stack can be populated with two synthetic projects and the full set of
browser-visible lifecycle and review states. The command creates `frontend-viewer`, `frontend-reviewer`,
`frontend-operator`, `frontend-admin`, and `frontend-manager`, all with the printed development-only
password. The manager owns the primary project without an ordinary project role; the administrator has the
global administrator role. It also creates ready and failed snapshots; running, completed, and failed runs;
completed and failed method executions; every agreement and certainty tier; annotation history and a
reproducible stale-revision conflict; and completed evaluation and JSON-export artifacts.

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

## Documentation

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
