FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src/ ./src/
COPY README.md LICENSE ./
COPY alembic.ini ./
COPY migrations/ ./migrations/
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
RUN groupadd -r app && useradd -r -g app app && \
    mkdir -p /app/data/artifacts && chown -R app:app /app

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH"

USER app

WORKDIR /app
CMD ["uvicorn", "gendertagger.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
