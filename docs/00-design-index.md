# Design document index

| Document | Purpose |
|---|---|
| [`01-architecture.md`](01-architecture.md) | System boundaries and component architecture |
| [`02-domain-model.md`](02-domain-model.md) | Core entities, identity, immutability, state machines |
| [`03-pydantic-contracts.md`](03-pydantic-contracts.md) | Canonical typed contracts and model boundaries |
| [`04-persistence.md`](04-persistence.md) | PostgreSQL/SQLAlchemy schema strategy |
| [`05-api.md`](05-api.md) | FastAPI resource model, endpoints, progress API |
| [`06-task-queue.md`](06-task-queue.md) | Celery/Redis execution, queues, idempotency, retries |
| [`07-methods-and-aggregation.md`](07-methods-and-aggregation.md) | Normative scientific pipeline behavior |
| [`08-ingestion-and-export.md`](08-ingestion-and-export.md) | Multi-format snapshot ingestion and reproducible exports |
| [`09-annotation-and-review.md`](09-annotation-and-review.md) | Human review/game behavior and audit trail |
| [`10-evaluation.md`](10-evaluation.md) | Benchmarks, metrics, agreement analysis |
| [`11-provenance-and-reproducibility.md`](11-provenance-and-reproducibility.md) | Provenance model and run manifests |
| [`12-deployment-and-operations.md`](12-deployment-and-operations.md) | Compose topology, storage, health, backup |
| [`13-auth-and-security.md`](13-auth-and-security.md) | Authentication, authorization, data boundaries |
| [`14-testing.md`](14-testing.md) | Test strategy and scientific regression fixtures |
| [`15-implementation-plan.md`](15-implementation-plan.md) | Ordered build plan for the IDE/coding agent |
| [`17-frontend-integration.md`](17-frontend-integration.md) | Vue/browser client contract and backend readiness |
| [`18-engineering-and-quality.md`](18-engineering-and-quality.md) | Toolchain, quality gates, CI, and delivery policy |
| [`19-coding-and-documentation-style.md`](19-coding-and-documentation-style.md) | Naming, docstrings, Markdown, and ADR style |
| [`20-method-adapters-reference.md`](20-method-adapters-reference.md) | Comprehensive reference for classification method adapters |
| [`21-production-promotion.md`](21-production-promotion.md) | Production promotion SOP and lifecycle |
| [`22-future-development.md`](22-future-development.md) | Deferred capabilities and the constraints they must respect |
| [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md) | Wireframe component/screen inventory and Vue transfer specification |
| [`24-frontend-delivery-plan.md`](24-frontend-delivery-plan.md) | Phase 8 milestones, open decisions, and frontend delivery risks |
| [`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md) | Visual system, scientific-vocabulary rendering, states, and accessibility |
| [`26-frontend-coding-guidelines.md`](26-frontend-coding-guidelines.md) | Vue 3 + TypeScript conventions, boundaries, testing, and validation |
| [`27-frontend-improvement-plan.md`](27-frontend-improvement-plan.md) | Shared foundations, per-view improvements, header content design, sidebar sequencing, and verification |
| [`28-aggregation-workflow-plan.md`](28-aggregation-workflow-plan.md) | Proposed automatic aggregation, reusable configuration, terminology, and reviewed-export implementation |
| [`29-wiki-gendersort-compatibility.md`](29-wiki-gendersort-compatibility.md) | Observable name-cleaning and assignment behavior, replacement provenance, and compatibility verification |
| [Architecture Decision Records](decisions/) | Accepted decisions and ADR template |
