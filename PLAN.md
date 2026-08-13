# Implementation plan

The authoritative phased plan is [`docs/15-implementation-plan.md`](docs/15-implementation-plan.md).

The first milestones are deliberately narrow:

1. establish repository guardrails, a locked toolchain, and initial CI;
2. freeze licensed legacy-characterization and approved reference fixtures from the existing pipeline;
3. implement Pydantic contracts and configuration;
4. port normalization and reference aggregation as pure tested logic;
5. only then introduce PostgreSQL, FastAPI, and Celery in successive vertical slices;
6. add Vue 3 + TypeScript + Vite only after the public API, async resource model, review concurrency, and OpenAPI contract are stable.

Do not scaffold the entire production stack in one pass. Preserve scientific equivalence first.
