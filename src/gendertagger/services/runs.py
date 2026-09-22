"""Application use cases for reproducible run resources."""

from dataclasses import dataclass
from uuid import UUID

from gendertagger.models.api import CursorPage
from gendertagger.models.run import MethodExecution, Run, RunCreate, RunCreateRequest
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.pagination import (
    CursorCodec,
    decode_creation_position,
    newest_first_page,
)
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
        cursor_codec: CursorCodec,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._method_registry = method_registry
        self._provenance = provenance
        self._cursor_codec = cursor_codec

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

    def list_runs(
        self,
        dataset_snapshot_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[Run]:
        """Return one newest-first opaque-cursor page of a snapshot's runs."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        resource = f"snapshot_runs:{dataset_snapshot_id}"
        after = decode_creation_position(self._cursor_codec, cursor, resource=resource)
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.projects.get_snapshot(dataset_snapshot_id) is None:
                msg = f"dataset snapshot {dataset_snapshot_id} does not exist"
                raise ResourceNotFoundError(msg)
            runs = unit_of_work.runs.list_runs(
                dataset_snapshot_id,
                limit=limit + 1,
                after=after,
            )
        return newest_first_page(self._cursor_codec, runs, limit=limit, resource=resource)

    def list_executions(self, run_id: UUID) -> list[MethodExecution]:
        """Return a run's method executions, or raise if the run is unknown."""
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.runs.get_run(run_id) is None:
                msg = f"run {run_id} does not exist"
                raise ResourceNotFoundError(msg)
            return unit_of_work.runs.list_method_executions(run_id)
