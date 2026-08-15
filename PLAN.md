# Current implementation plan

This file is a brief status summary only. The authoritative, current phased plan is in [`docs/15-implementation-plan.md`](docs/15-implementation-plan.md). That document is the source of truth for scope, sequencing, and exit criteria.

## Status at a glance

- Phase 0: repository guardrails, baseline capture, and fixture governance are complete.
- Phase 1: contracts, normalization, aggregation, and domain regression behavior are complete.
- Phase 2: PostgreSQL persistence and migration layer are complete.
- Phase 3: FastAPI vertical slice and OpenAPI conventions are complete.
- Phase 4: Celery execution and async workflow controls are complete.
- Phase 5: method migration and asynchronous import/aggregation paths are complete.
- Phase 6: evaluation and export are complete.
- Phase 7: deployment hardening is complete.
- Phase 8: the Vue 3 + TypeScript + Vite client is the active work; its backend prerequisites are
  done, and the client itself is not started.

## Current implementation focus

Phases 0 through 7 are complete. All nine reference method adapters are implemented and registered
alongside the experimental HIVOTO-XGBoost adapter, and the asynchronous snapshot-import, lookup-asset,
method-execution, reference-aggregation, evaluation, and export paths all run end to end through the
persisted API-to-worker workflow.

Active work is Phase 8, the annotation and review client. Its backend prerequisites are already met:
the review-items query API is stable and review-stream revision conflicts return `409`. The remaining
Phase 8 items are frontend work, and `frontend/` is still a placeholder. The second active track is
operating the stack in production following [`docs/21-production-promotion.md`](docs/21-production-promotion.md).

The repository-specific guidance in [`AGENTS.md`](AGENTS.md) and the authoritative phased plan in [`docs/15-implementation-plan.md`](docs/15-implementation-plan.md) remain the source of truth. This summary should be read as a status note, not as the canonical roadmap.

## Rules

- keep scientific equivalence and reproducibility ahead of feature expansion;
- treat the existing backend/domain implementation as real progress rather than as a placeholder;
- record deferred ideas in [`docs/22-future-development.md`](docs/22-future-development.md) rather
  than reopening scope inside the design documents;
- do not start new scope churn without reconciling it against the authoritative phased plan.
