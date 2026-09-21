# Agent implementation instructions

This repository is an architecture-first scaffold. Treat the design documents as the current specification.

## Non-negotiable architecture rules

1. Pydantic models define canonical contracts.
2. FastAPI is the canonical public interface and application composition root.
3. SQLAlchemy models are persistence models only. Do not expose them from API or domain services.
4. Celery tasks call application services directly. They do not call FastAPI over HTTP.
5. Task messages should contain small, validated Pydantic envelopes with identifiers, not large datasets.
6. A `DatasetSnapshot` is immutable after successful import.
7. A person is canonically identified by TEI `xml:id` within its project. Do not invent a global person-identity layer.
8. `Prediction` rows are immutable method outputs. Never overwrite them with aggregation or human review.
9. `unknown`, `abstain`, and `error` are distinct concepts.
10. Per-method `method_confidence` values are method-specific and must not be treated as globally calibrated probabilities.
11. Preserve raw method output and normalization provenance.
12. The default aggregation must reproduce the published reference behavior before alternative strategies are added.
13. Human annotations are auditable append-only decisions; corrections supersede earlier annotations rather than mutating history.
14. Imports, runs, aggregations, evaluations, and exports must be reproducible from persisted configuration/provenance.
15. Default deployment must support local/private operation, including out-of-band locally hosted LLMs (via `LLM_BASE_URL`) and local authority snapshots.
16. The Vue UI is an ordinary `/api/v1` client. Do not create page-specific business logic or expose ORM/Celery/filesystem details for it.
17. Treat OpenAPI as a public contract and generate frontend transport types/client code from it.
18. Long-running HTTP commands return persisted domain resources (`202 Accepted` where appropriate), never Celery task IDs.
19. Large collection endpoints use server-side query/filter/sort and cursor pagination.
20. Human annotation history remains append-only; stale review writes fail with `409 Conflict` using the review revision.
21. Prefer same-origin production deployment and secure HTTP-only browser sessions with CSRF protection.

## Implementation order

Follow `docs/15-implementation-plan.md`. Do not begin with the frontend or Docker Compose. Establish contracts and tests first.

## Expected stack

- Python 3.11+
- FastAPI
- Pydantic v2 / pydantic-settings
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Celery
- Redis
- lxml
- YAML configuration validated through Pydantic
- pytest
- Vue 3 + TypeScript + Vite (Phase 8, not before)

Runtime dependency versions are deliberately not yet selected in this scaffold. Add compatible direct
constraints and refresh the committed lockfile when implementation begins; record the exact resolved
environment in run provenance.

## Engineering quality gates

Follow `docs/18-engineering-and-quality.md` and `CONTRIBUTING.md`. Keep `uv.lock` committed and run the locked
documentation, contract-naming, package-initializer, Ruff, mypy, Import Linter, pytest, and package-build
checks before handing off implementation changes. Naming, docstring, package-initializer, Markdown, and ADR
conventions are defined in `docs/19-coding-and-documentation-style.md`. CI grows with each implementation
phase; do not defer basic automated checks until deployment hardening.

## Scientific behavior

Before modifying labels, normalization, aggregation, authority overrides, certainty tiers, TEI output semantics, or evaluation definitions, update the relevant design document and add an ADR.
