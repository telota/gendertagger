FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src/ ./src/
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH"

RUN groupadd -r app && useradd -r -g app app && \
    mkdir -p /app/data/artifacts && chown -R app:app /app
USER app

WORKDIR /app
CMD ["uvicorn", "gendertagger.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
