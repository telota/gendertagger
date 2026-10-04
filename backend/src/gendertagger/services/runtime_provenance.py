"""Capture the installed execution environment and actual worker process identity."""

from importlib.metadata import distributions, version
from os import getpid
from platform import python_version
from socket import gethostname

from gendertagger.models.run import WorkerProvenance


def installed_dependency_versions() -> dict[str, str]:
    """Record exact installed distribution versions in deterministic name order."""
    return dict(
        sorted(
            (distribution.metadata["Name"].lower(), distribution.version)
            for distribution in distributions()
        )
    )


def capture_worker_provenance(
    *,
    code_git_commit: str,
    dependency_lock_sha256: str,
    container_image_digest: str | None = None,
) -> WorkerProvenance:
    """Bind configured build identity to the installed environment and current process."""
    return WorkerProvenance(
        code_git_commit=code_git_commit,
        application_version=version("gendertagger"),
        python_version=python_version(),
        dependency_lock_sha256=dependency_lock_sha256,
        dependency_versions=installed_dependency_versions(),
        container_image_digest=container_image_digest,
        hostname=gethostname(),
        process_id=getpid(),
    )
