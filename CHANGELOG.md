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
  [`SCAFFOLD.json`](SCAFFOLD.json) design manifest.
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
- Test scaffold under [`tests/`](tests/) with a packaging smoke test and policy-script regression tests.
- A validated example run configuration at [`config/example.yaml`](config/example.yaml), plus deployment,
  frontend, and persistence placeholders in [`frontend/README.md`](frontend/README.md), `migrations/`, and
  `deploy/`.
- Reproducible dependency management via `uv.lock`, hatchling builds, and PEP 735 dependency groups.
- Authenticated FastAPI `/api/v1` resources for projects, immutable TEI snapshot imports, runs, the method
  registry, aggregations/results, append-only annotations, and server-filtered review lists; public contracts
  include cursor pagination, normalized error envelopes, a committed OpenAPI snapshot, and typed `CurrentUser`.

### Changed

- Restored the documented local quality gates with repository-owned pre-commit/pre-push hooks, YAML
  front-matter-aware documentation validation, valid headings in maintained Markdown, and explicit Ruff
  exclusions for preserved research notebooks and upstream reference snapshots.
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

### Removed

- Legacy research pipeline: the classification implementation under `src/gendertagger/backend/`, and the
  analysis, plotting, and orchestration scripts in `scripts/` (including `run_all_methods.py`,
  `aggregate_results.py`, `benchmark.py`, `agreements.py`, `record_agreement.py`, `plot_kappa_heatmap.py`,
  and `poster_pies.py`).
- Generated `output/` artifacts, including per-method result CSVs, Cohen's kappa results, agreement
  summaries, and poster figures.
- `docs/QUICK_START.md` and `docs/UI_GUIDE.md`, superseded by the design documents.
- `requirements.txt` and `requirements-dev.txt`, replaced by `pyproject.toml` dependency groups and
  `uv.lock`.

Removed pipeline code and result artifacts remain available in version control history at commit
`36522b8`; restoring the legacy scientific fixture is a prerequisite of the implementation plan.
