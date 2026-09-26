# gendertagger specification

This file is the short normative entry point. Detailed rationale lives in `docs/`. For a local Docker
Compose quickstart, including provisioning method data, see [`README.md`](README.md#quickstart).

## Product

A local-first, reproducible, human-in-the-loop service for enriching TEI/XML person registers with gender annotations using multiple independent methods, uncertainty-aware aggregation, editorial review, evaluation, and provenance-preserving export.

## Mandatory architecture

- FastAPI is the canonical public interface and application composition root.
- Pydantic is the canonical contract layer.
- The Vue 3 + TypeScript + Vite UI is an ordinary client of `/api/v1`, never a privileged backend layer.
- OpenAPI is the machine-readable client contract; frontend transport types/client code are generated from it.
- SQLAlchemy/PostgreSQL are persistence infrastructure, not the domain/API model.
- Celery/Redis execute asynchronous batched work.
- Projects contain immutable DatasetSnapshots.
- TEI `xml:id` is canonical within a Project.
- Runs contain independently rerunnable MethodExecutions.
- Predictions are immutable evidence.
- Aggregation is versioned and rerunnable without rerunning methods.
- Human annotations are append-only and auditable.
- Original TEI and generated artifacts are checksummed and preserved.
- Long-running imports/runs/evaluations/exports are persisted resources created asynchronously; clients never depend on Celery task IDs.
- Large collections use server-side filtering/search/sorting and cursor pagination.
- Annotation writes are append-only and use review revisions for optimistic concurrency.
- Production supports same-origin frontend/API deployment; browser auth should use secure HTTP-only sessions with CSRF protection.

## Canonical classification semantics

Labels:

`male | female | unknown | institution`

Method execution result status:

`success | abstain | error`

A substantive `unknown` is not an abstention. Method-specific confidence is stored as `method_confidence` and is not assumed to be calibrated across methods.

## Reference aggregation

The default implementation reproduces the published reference strategy in
`docs/07-methods-and-aggregation.md`; alternative strategies must not change that reference behavior.
