"""Application use cases for reproducible run resources."""

from dataclasses import dataclass
from uuid import UUID

from gendertagger.models.run import Run, RunCreate, RunCreateRequest
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.unit_of_work import UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class RunProvenance:
    """Server-owned runtime identity persisted with every created run."""

    code_git_commit: str
    application_version: str
    python_version: str
    dependency_lock_sha256: str
    container_image_digest: str | None = None


class RunService:
    """Validate, persist, and read runs without scheduling Phase 4 work."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        method_registry: MethodRegistry,
        provenance: RunProvenance,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._method_registry = method_registry
        self._provenance = provenance

    def create_run(self, command: RunCreateRequest) -> Run:
        """Persist one created run after resolving every registered method config."""
        resolved_config = self._method_registry.resolve_run_config(command.config)
        with self._unit_of_work_factory() as unit_of_work:
            run = unit_of_work.runs.add_run(
                RunCreate(
                    dataset_snapshot_id=command.dataset_snapshot_id,
                    resolved_config=resolved_config,
                    code_git_commit=self._provenance.code_git_commit,
                    application_version=self._provenance.application_version,
                    container_image_digest=self._provenance.container_image_digest,
                    python_version=self._provenance.python_version,
                    dependency_lock_sha256=self._provenance.dependency_lock_sha256,
                )
            )
            unit_of_work.commit()
        return run

    def get_run(self, run_id: UUID) -> Run:
        """Return one persisted run or raise a resource-level not-found failure."""
        with self._unit_of_work_factory() as unit_of_work:
            run = unit_of_work.runs.get_run(run_id)
        if run is None:
            msg = f"run {run_id} does not exist"
            raise ResourceNotFoundError(msg)
        return run
