# ADR-0004: PostgreSQL + Celery + Redis

**Status:** Accepted

## Context

The service needs durable relational state for reproducibility and asynchronous execution for CPU, GPU, and
external methods. Queue coordination must not become the authoritative store for scientific results.

## Decision

Use PostgreSQL for durable state and scientific results. Use Celery for asynchronous work with Redis as broker/coordination layer.

Separate CPU, GPU, LLM/external classes through queues as operationally useful.

## Consequences

- conventional, well-understood infrastructure
- retries and batch execution are explicit
- Redis loss does not destroy persisted scientific results
- no additional workflow engine or event bus in v1
