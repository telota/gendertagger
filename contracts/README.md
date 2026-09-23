# Public contracts

Artifacts that both the backend and the frontend depend on, owned by neither.

- [`openapi-v1.json`](openapi-v1.json) is the committed snapshot of the `/api/v1` OpenAPI document. The
  backend contract test fails when it differs from the live API, and the frontend generates its transport
  types from it. After a contract change, regenerate both, from `backend/`:

  ```bash
  uv run --locked python scripts/update_openapi_snapshot.py
  npm --prefix ../frontend run api:generate
  ```

Review a diff here as a public API change; see [`docs/05-api.md`](../docs/05-api.md).
