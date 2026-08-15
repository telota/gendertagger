# Current implementation plan

This file is a brief status summary only. The authoritative, current phased plan is in [`docs/15-implementation-plan.md`](docs/15-implementation-plan.md). That document is the source of truth for scope, sequencing, and exit criteria.

## Status at a glance

- Phase 0: repository guardrails, baseline capture, and fixture governance are complete.
- Phase 1: contracts, normalization, aggregation, and domain regression behavior are complete.
- Phase 2: PostgreSQL persistence and migration layer are complete.
- Phase 3: FastAPI vertical slice and OpenAPI conventions are complete.
- Phase 4: Celery execution and async workflow controls are complete.
- Phase 5: method migration and asynchronous import/aggregation paths are complete.
- Phase 6: evaluation and export are not started.
- Phase 7: deployment hardening is complete.
- Phase 8: Vue 3 + TypeScript + Vite frontend work is not started.

## Current implementation focus

The codebase is materially ahead of the older phase summary. The repository already contains substantial implementation work across the domain model, persistence layer, API, Celery orchestration, task/dispatch patterns, and the scientific reference pipeline, so this is no longer a greenfield scaffold. The remaining work is therefore narrower and more targeted: close the last scientific compatibility and governance gaps, finish the remaining Phase 5 adapter work, and complete the post-API production features rather than rebuild the stack from scratch.

The repository-specific guidance in [`AGENTS.md`](AGENTS.md) and the authoritative phased plan in [`docs/15-implementation-plan.md`](docs/15-implementation-plan.md) remain the source of truth. This summary should be read as a status note, not as the canonical roadmap.

## Rules

- keep scientific equivalence and reproducibility ahead of feature expansion;
- treat the existing backend/domain implementation as real progress rather than as a placeholder;
- do not treat evaluation/export or the Vue client as "not started" just because they are still being finished; they are explicitly deferred milestones, not the primary current implementation surface;
- do not start new scope churn without reconciling it against the authoritative phased plan.
