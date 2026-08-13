# ADR-0001: Pydantic contracts and FastAPI are central

**Status:** Accepted

## Context

The existing system is a Python pipeline. The service must add API, workers, CLI, persistence, and UI without creating divergent data models.

## Decision

Pydantic models are the canonical application contracts. FastAPI is the canonical public interface and composition entry point. SQLAlchemy models remain persistence-only.

Celery, CLI, import/export, and methods reuse the same service/domain contracts rather than implementing parallel business logic.

## Consequences

- OpenAPI is generated from the same contracts used by the application.
- ORM schema changes do not automatically become API changes.
- mapping code between ORM and Pydantic is accepted as useful boundary code.
- large task payloads are still avoided; Celery uses small Pydantic envelopes with IDs.
