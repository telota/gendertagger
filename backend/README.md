# gendertagger backend

The Python service behind gendertagger: the FastAPI `/api/v1` application, the Celery workers, the
classification method adapters, and the PostgreSQL persistence with its Alembic migrations.

This directory is the Python project root: run backend commands from here, for example
`uv run --locked pytest`. The project overview, setup, and design documents live at the repository root;
see the top-level `README.md`, `CONTRIBUTING.md`, and `docs/`.
