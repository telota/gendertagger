# Future browser UI

This directory is intentionally implementation-empty.

The accepted target is **Vue 3 + TypeScript + Vite**, introduced only after the backend contracts and first asynchronous vertical slice are stable.

Read:

- `../docs/17-frontend-integration.md`
- `../docs/05-api.md`
- `../docs/03-pydantic-contracts.md`
- `../docs/09-annotation-and-review.md`
- `../docs/decisions/ADR-0006-vue-browser-client-boundary.md`

When implementation begins, the frontend must consume `/api/v1` through OpenAPI-generated transport types/client code. It must not duplicate scientific logic, talk to Celery/Redis directly, or depend on database/storage internals.
