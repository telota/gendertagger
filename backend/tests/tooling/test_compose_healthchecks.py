from __future__ import annotations

import shlex
from pathlib import Path

import yaml

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_worker_healthcheck_expands_its_own_container_hostname() -> None:
    compose = yaml.safe_load((_REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    kind, command = compose["services"]["worker-cpu"]["healthcheck"]["test"]

    assert kind == "CMD-SHELL"
    # Escape Compose interpolation, then expand in the container, not on the host.
    assert '"celery@$$HOSTNAME"' in command
    assert shlex.split(command) == [
        "celery",
        "-A",
        "gendertagger.tasks.celery_app",
        "inspect",
        "ping",
        "-d",
        "celery@$$HOSTNAME",
    ]
