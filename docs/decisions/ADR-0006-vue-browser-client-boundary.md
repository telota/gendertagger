# ADR-0006: Vue browser client uses the public FastAPI contract

**Status:** Accepted

## Context

A Vue-based review and annotation UI is planned after the service core is established. The backend must not become a collection of page-specific helper endpoints or expose infrastructure details simply because the first browser client is colocated with it.

## Decision

The browser UI will use Vue 3 + TypeScript + Vite and consume the same versioned `/api/v1` FastAPI interface available to other clients.

FastAPI/OpenAPI is the machine-readable contract. TypeScript transport types/client code should be generated from OpenAPI when frontend work begins.

Long-running work is represented by persisted domain resources and `202 Accepted` responses; clients never depend on Celery task IDs. Server-Sent Events provide optional server-to-client progress while PostgreSQL remains authoritative.

Potentially large lists use server-side query/filter/sort and cursor pagination. Human annotations remain append-only; concurrent review uses an explicit review revision and returns `409 Conflict` on stale writes.

Production should prefer same-origin deployment behind one reverse proxy. Browser authentication should prefer secure HTTP-only sessions with CSRF protection rather than long-lived tokens in browser storage.

## Consequences

- Vue can be added later without changing core application services.
- CLI and external integrations retain first-class API semantics.
- frontend implementation details cannot become scientific business logic.
- API schema stability and OpenAPI contract tests become important.
- reverse-proxy configuration must support SSE and same-origin routing.
- append-only annotation history remains compatible with multi-user review.
