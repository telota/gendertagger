"""Application entry point and healthchecks."""

import os

from fastapi import FastAPI, Response, status
from sqlalchemy import text

from gendertagger.api.app import create_app

app = create_app()


@app.get("/health", tags=["health"])
async def health() -> Response:
    """Check if the API process is alive."""
    return Response(content="OK", status_code=status.HTTP_200_OK)


@app.get("/ready", tags=["health"])
def ready() -> Response:
    """Check if database and artifact storage are usable."""
    # Check artifact storage
    settings = app.state.settings
    if not os.path.exists(settings.artifact_root):
        return Response(
            content="Artifact storage unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Check DB using unit_of_work_factory
    uow_factory = app.state.unit_of_work_factory
    try:
        with uow_factory() as uow:
            uow.session.execute(text("SELECT 1"))
    except Exception:
        return Response(
            content="Database unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(content="OK", status_code=status.HTTP_200_OK)
