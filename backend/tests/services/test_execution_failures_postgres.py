from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Connection, func, select
from tests.factories import tei_person_input
from tests.seeding import (
    seed_artifact,
    seed_project,
    seed_ready_snapshot,
    seed_run,
    seed_worker_provenance,
)

from gendertagger.config.run import ExecutionConfig, MethodRunConfig, RunConfig
from gendertagger.db.rows.executions import PredictionRow
from gendertagger.methods.adapters.gnd import GndConfig, GndMethod
from gendertagger.methods.adapters.hf_distilbert import HfDistilbertConfig, HfDistilbertMethod
from gendertagger.methods.adapters.parenthetical_qualifier import (
    ParentheticalQualifierConfig,
    ParentheticalQualifierMethod,
)
from gendertagger.methods.base import MethodConfig, MethodContractError
from gendertagger.methods.gnd_snapshot import compile_gnd_marcxml_lookup
from gendertagger.models.artifact import ModelManifestMember, ModelManifestMetadata
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.models.run import (
    METHOD_EXECUTION_FAILURE_CLASS,
    Progress,
    RunCreate,
    WorkerProvenance,
)
from gendertagger.services.execution import (
    BatchExecutor,
    RunScheduler,
    ScheduledBatch,
    TransientBatchError,
)
from gendertagger.services.method_registry import (
    MethodRegistration,
    MethodRegistry,
    default_method_registry,
)
from gendertagger.services.model_assets import RegisteredModelDirectoryResolver
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


class _EmptyConfig(MethodConfig):
    pass


class _TransientAdapter:
    descriptor = MethodDescriptor(
        name="flaky_method", implementation_version="v1", normalization_version="v1"
    )
    config_model = _EmptyConfig

    def __init__(self, message: str = "transient broker outage") -> None:
        self._message = message

    def predict_batch(
        self, people: Sequence[PersonInput], config: _EmptyConfig
    ) -> list[PredictionResult]:
        del people, config
        raise RuntimeError(self._message)


class _PermanentAdapter:
    descriptor = MethodDescriptor(
        name="broken_method", implementation_version="v1", normalization_version="v1"
    )
    config_model = _EmptyConfig

    def __init__(self) -> None:
        self.call_count = 0

    def predict_batch(
        self, people: Sequence[PersonInput], config: _EmptyConfig
    ) -> list[PredictionResult]:
        self.call_count += 1
        del people, config
        raise MethodContractError("adapter returned the wrong shape")


def _registration(adapter: object, *, logical_type: str | None = None) -> MethodRegistration:
    return MethodRegistration(
        descriptor=adapter.descriptor,  # type: ignore[attr-defined]
        config_model=adapter.config_model,  # type: ignore[attr-defined]
        adapter=adapter,  # type: ignore[arg-type]
        queue_name="cpu",
        batch_size=100,
        data_artifact_logical_type=logical_type,
    )


def _seed_run(
    factory: UnitOfWorkFactory,
    *,
    methods: list[MethodRunConfig],
    execution_config: ExecutionConfig | None = None,
    historical_dependencies: bool = False,
) -> UUID:
    config = RunConfig(methods=methods, execution=execution_config or ExecutionConfig())
    with factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="fail")
        snapshot = seed_ready_snapshot(
            unit_of_work,
            project.id,
            [tei_person_input(tei_id="p01", surname="Frölich (Frau des Heinrich)")],
        )
        if historical_dependencies:
            provenance = seed_worker_provenance()
            run = unit_of_work.runs.add_run(
                RunCreate(
                    dataset_snapshot_id=snapshot.id,
                    resolved_config=config,
                    **provenance.model_dump(
                        exclude={"hostname", "process_id", "dependency_versions"}
                    ),
                )
            )
        else:
            run = seed_run(unit_of_work, snapshot.id, config)
        unit_of_work.commit()
        return run.id


def _executor(factory: UnitOfWorkFactory, registry: MethodRegistry) -> BatchExecutor:
    return BatchExecutor(
        unit_of_work_factory=factory,
        method_registry=registry,
        clock=lambda: NOW,
        worker_provenance=seed_worker_provenance(),
    )


def _scheduled(
    factory: UnitOfWorkFactory, registry: MethodRegistry, run_id: UUID
) -> list[ScheduledBatch]:
    scheduler = RunScheduler(
        unit_of_work_factory=factory, method_registry=registry, clock=lambda: NOW
    )
    return scheduler.schedule_run(run_id)


def test_transient_failure_below_max_attempts_raises_for_retry(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    registry = MethodRegistry([_registration(_TransientAdapter())])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="flaky_method")])
    scheduled = _scheduled(factory, registry, run_id)

    with pytest.raises(TransientBatchError):
        _executor(factory, registry).execute(
            scheduled[0].message(), worker_task_id="w", attempt_count=1, max_attempts=3
        )

    with factory() as unit_of_work:
        batch = unit_of_work.runs.get_task_batch(scheduled[0].task_batch_id)
    assert batch is not None
    assert batch.status is TaskBatchStatus.pending  # rolled back for retry
    assert batch.worker_provenance is None
    assert batch.worker_task_id is None


def test_transient_failure_at_max_attempts_fails_the_batch(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    registry = MethodRegistry([_registration(_TransientAdapter())])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="flaky_method")])
    scheduled = _scheduled(factory, registry, run_id)

    failed = _executor(factory, registry).execute(
        scheduled[0].message(), worker_task_id="w", attempt_count=3, max_attempts=3
    )

    assert failed.status is TaskBatchStatus.failed
    assert failed.failure_class == "RuntimeError"
    assert failed.error_count == 1
    with factory() as unit_of_work:
        execution = unit_of_work.runs.get_method_execution(scheduled[0].method_execution_id)
        run = unit_of_work.runs.get_run(run_id)
    assert execution is not None
    assert execution.status is MethodExecutionStatus.failed
    assert execution.failed_count == 1
    assert execution.progress.total == 1
    assert execution.progress.completed == 0
    assert execution.progress.failed == 1
    assert execution.progress.percentage == 100
    assert run is not None
    assert run.status is RunStatus.completed_with_errors
    assert run.progress.total == 1
    assert run.progress.completed == 0
    assert run.progress.failed == 1
    assert run.progress.percentage == 100


def test_terminal_batch_and_execution_diagnostics_redact_url_credentials(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    adapter = _TransientAdapter("redis://worker:credential-marker@broker:6379/0 unavailable")
    registry = MethodRegistry([_registration(adapter)])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="flaky_method")])
    scheduled = _scheduled(factory, registry, run_id)

    failed = _executor(factory, registry).execute(
        scheduled[0].message(), worker_task_id="w", attempt_count=3, max_attempts=3
    )

    assert failed.failure_diagnostic == (
        "RuntimeError: redis://<redacted>@broker:6379/0 unavailable"
    )
    with factory() as unit_of_work:
        execution = unit_of_work.runs.get_method_execution(scheduled[0].method_execution_id)
        stored_batch = unit_of_work.runs.get_task_batch(scheduled[0].task_batch_id)
    assert execution is not None
    assert stored_batch is not None
    assert stored_batch.failure_diagnostic == failed.failure_diagnostic
    assert execution.failure_diagnostic is not None
    assert "credential-marker" not in execution.failure_diagnostic
    assert "redis://<redacted>@broker:6379/0 unavailable" in execution.failure_diagnostic


def test_permanent_failure_fails_the_batch_without_retry(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    registry = MethodRegistry([_registration(_PermanentAdapter())])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="broken_method")])
    scheduled = _scheduled(factory, registry, run_id)

    failed = _executor(factory, registry).execute(
        scheduled[0].message(), worker_task_id="w", attempt_count=1, max_attempts=3
    )

    assert failed.status is TaskBatchStatus.failed
    assert failed.failure_class == "MethodContractError"
    assert failed.error_count == 1


def test_redelivery_does_not_reopen_a_failed_batch(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    adapter = _PermanentAdapter()
    registry = MethodRegistry([_registration(adapter)])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="broken_method")])
    scheduled = _scheduled(factory, registry, run_id)
    executor = _executor(factory, registry)

    first = executor.execute(
        scheduled[0].message(), worker_task_id="w1", attempt_count=1, max_attempts=3
    )
    redelivery = executor.execute(
        scheduled[0].message(), worker_task_id="w2", attempt_count=2, max_attempts=3
    )

    assert first.status is TaskBatchStatus.failed
    assert redelivery.status is TaskBatchStatus.failed
    assert redelivery.error_count == 1
    assert redelivery.worker_task_id == "w1"
    assert redelivery.worker_provenance == first.worker_provenance == seed_worker_provenance()
    assert adapter.call_count == 1


def test_partial_failure_preserves_the_successful_method(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, connection = postgres_unit_of_work
    registry = MethodRegistry(
        [*default_method_registry().registrations, _registration(_PermanentAdapter())]
    )
    run_id = _seed_run(
        factory,
        methods=[
            MethodRunConfig(name="parenthetical_qualifier"),
            MethodRunConfig(name="broken_method"),
        ],
    )
    scheduled = _scheduled(factory, registry, run_id)
    assert len(scheduled) == 2

    executor = _executor(factory, registry)
    for batch in scheduled:
        executor.execute(batch.message(), worker_task_id="w", attempt_count=3, max_attempts=3)

    with factory() as unit_of_work:
        run = unit_of_work.runs.get_run(run_id)
        executions = {}
        for batch in scheduled:
            execution = unit_of_work.runs.get_method_execution(batch.method_execution_id)
            assert execution is not None
            executions[execution.method_name] = execution
    assert run is not None
    assert run.status is RunStatus.completed_with_errors
    assert executions["parenthetical_qualifier"].status is MethodExecutionStatus.completed
    assert executions["broken_method"].status is MethodExecutionStatus.failed

    preserved = connection.execute(
        select(func.count())
        .select_from(PredictionRow)
        .where(PredictionRow.method_execution_id == executions["parenthetical_qualifier"].id)
    ).scalar_one()
    assert preserved == 1  # the successful method's evidence survives


def test_fail_run_flag_fails_the_run_on_method_failure(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    registry = MethodRegistry([_registration(_PermanentAdapter())])
    run_id = _seed_run(
        factory,
        methods=[MethodRunConfig(name="broken_method")],
        execution_config=ExecutionConfig(fail_run_on_optional_method_error=True),
    )
    scheduled = _scheduled(factory, registry, run_id)

    _executor(factory, registry).execute(
        scheduled[0].message(), worker_task_id="w", attempt_count=3, max_attempts=3
    )

    with factory() as unit_of_work:
        run = unit_of_work.runs.get_run(run_id)
    assert run is not None
    assert run.status is RunStatus.failed
    assert run.failure_class == METHOD_EXECUTION_FAILURE_CLASS
    assert run.failure_diagnostic is not None


class _CountingQualifier(ParentheticalQualifierMethod):
    def __init__(self) -> None:
        self.call_count = 0

    def predict_batch(
        self, people: Sequence[PersonInput], config: ParentheticalQualifierConfig
    ) -> list[PredictionResult]:
        self.call_count += 1
        return super().predict_batch(people, config)


@pytest.mark.parametrize(
    ("identity", "changed_value"),
    [
        ("implementation_version", "deployed-v2"),
        ("normalization_version", "normalization-v2"),
        ("code_git_commit", "e" * 40),
        ("application_version", "1.2.3"),
        ("python_version", "3.12.0"),
        ("dependency_lock_sha256", "e" * 64),
        ("dependency_versions", {"pydantic": "2.12.0", "sqlalchemy": "2.0.0"}),
        ("container_image_digest", "sha256:" + "e" * 64),
    ],
)
def test_worker_identity_mismatch_fails_before_prediction_and_survives_redelivery(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
    identity: str,
    changed_value: object,
) -> None:
    factory, connection = postgres_unit_of_work
    accepted_adapter = _CountingQualifier()
    accepted_registry = MethodRegistry([_registration(accepted_adapter)])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="parenthetical_qualifier")])
    (scheduled,) = _scheduled(factory, accepted_registry, run_id)
    worker_adapter = _CountingQualifier()
    worker = seed_worker_provenance()
    if identity in {"implementation_version", "normalization_version"}:
        worker_adapter.descriptor = MethodDescriptor.model_validate(
            {**worker_adapter.descriptor.model_dump(), identity: changed_value}
        )
    else:
        worker = WorkerProvenance.model_validate({**worker.model_dump(), identity: changed_value})
    failed = BatchExecutor(
        unit_of_work_factory=factory,
        method_registry=MethodRegistry([_registration(worker_adapter)]),
        worker_provenance=worker,
        clock=lambda: NOW,
    ).execute(scheduled.message(), worker_task_id="incompatible-worker", attempt_count=1)

    assert failed.status is TaskBatchStatus.failed
    assert failed.failure_class == "IncompatibleWorkerError"
    assert failed.failure_diagnostic is not None
    assert identity in failed.failure_diagnostic
    assert failed.worker_provenance == worker
    assert failed.error_count == 1
    assert worker_adapter.call_count == 0
    redelivered = _executor(factory, accepted_registry).execute(
        scheduled.message(), worker_task_id="compatible-redelivery", attempt_count=2
    )
    assert redelivered == failed
    assert accepted_adapter.call_count == 0
    with factory() as unit_of_work:
        persisted = unit_of_work.runs.get_task_batch(scheduled.task_batch_id)
        execution = unit_of_work.runs.get_method_execution(scheduled.method_execution_id)
        run = unit_of_work.runs.get_run(run_id)
    assert persisted == failed
    assert execution is not None
    assert execution.status is MethodExecutionStatus.failed
    assert run is not None
    assert run.status is RunStatus.completed_with_errors
    assert (
        connection.execute(
            select(func.count())
            .select_from(PredictionRow)
            .where(PredictionRow.method_execution_id == scheduled.method_execution_id)
        ).scalar_one()
        == 0
    )


def test_historical_run_without_dependency_evidence_is_not_relabelled(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, connection = postgres_unit_of_work
    adapter = _CountingQualifier()
    registry = MethodRegistry([_registration(adapter)])
    run_id = _seed_run(
        factory,
        methods=[MethodRunConfig(name="parenthetical_qualifier")],
        historical_dependencies=True,
    )
    (scheduled,) = _scheduled(factory, registry, run_id)

    failed = _executor(factory, registry).execute(
        scheduled.message(), worker_task_id="historical-worker", attempt_count=1
    )

    assert failed.failure_class == "IncompatibleWorkerError"
    assert failed.worker_provenance == seed_worker_provenance()
    assert adapter.call_count == 0
    with factory() as unit_of_work:
        run = unit_of_work.runs.get_run(run_id)
    assert run is not None
    assert run.dependency_versions is None
    assert (
        connection.execute(
            select(func.count())
            .select_from(PredictionRow)
            .where(PredictionRow.method_execution_id == scheduled.method_execution_id)
        ).scalar_one()
        == 0
    )


class _AssetResolver:
    def __init__(self, paths: dict[tuple[str, str], Path]) -> None:
        self.paths = paths

    def materialize(self, logical_type: str, sha256: str) -> Path:
        return self.paths[(logical_type, sha256)]


class _CountingGnd(GndMethod):
    def __init__(self, resolver: _AssetResolver) -> None:
        super().__init__(lookup_asset_resolver=resolver)
        self.call_count = 0

    def predict_batch(
        self, people: Sequence[PersonInput], config: GndConfig
    ) -> list[PredictionResult]:
        self.call_count += 1
        return super().predict_batch(people, config)


class _CountingDistilbert(HfDistilbertMethod):
    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def predict_batch(
        self, people: Sequence[PersonInput], config: HfDistilbertConfig
    ) -> list[PredictionResult]:
        self.call_count += 1
        return super().predict_batch(people, config)


def _assert_asset_rejected(
    factory: UnitOfWorkFactory,
    connection: Connection,
    registry: MethodRegistry,
    scheduled: ScheduledBatch,
    *,
    resolver: _AssetResolver,
    directory_resolver: RegisteredModelDirectoryResolver | None = None,
) -> None:
    failed = BatchExecutor(
        unit_of_work_factory=factory,
        method_registry=registry,
        worker_provenance=seed_worker_provenance(),
        lookup_asset_resolver=resolver,
        model_directory_resolver=directory_resolver,
        clock=lambda: NOW,
    ).execute(scheduled.message(), worker_task_id="asset-worker", attempt_count=1)
    assert failed.status is TaskBatchStatus.failed
    assert failed.failure_class == "IncompatibleWorkerError"
    assert failed.failure_diagnostic
    assert failed.worker_provenance == seed_worker_provenance()
    with factory() as unit_of_work:
        persisted = unit_of_work.runs.get_task_batch(scheduled.task_batch_id)
    assert persisted == failed
    assert (
        connection.execute(
            select(func.count())
            .select_from(PredictionRow)
            .where(PredictionRow.method_execution_id == scheduled.method_execution_id)
        ).scalar_one()
        == 0
    )


@pytest.mark.parametrize("drift", [False, True])
def test_worker_verifies_pinned_lookup_bytes_not_a_newer_artifact(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
    tmp_path: Path,
    drift: bool,
) -> None:
    factory, connection = postgres_unit_of_work
    source = tmp_path / "gnd.xml"
    source.write_bytes(b"""<collection xmlns="http://www.loc.gov/MARC21/slim"><record>
<leader>00000n000000000000000000</leader><controlfield tag="001">person-1</controlfield>
<datafield tag="075"><subfield code="b">piz</subfield></datafield>
<datafield tag="100"><subfield code="a">Muster, Karl</subfield></datafield>
<datafield tag="375"><subfield code="a">1</subfield><subfield code="2">iso5218</subfield></datafield>
</record><record>
<leader>00000n000000000000000000</leader><controlfield tag="001">org-1</controlfield>
<datafield tag="075"><subfield code="b">kiz</subfield></datafield>
<datafield tag="110"><subfield code="a">Beispielverein</subfield></datafield>
</record></collection>""")
    lookup = tmp_path / "lookup.sqlite3"
    compile_gnd_marcxml_lookup(
        source, lookup, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()
    )
    digest = hashlib.sha256(lookup.read_bytes()).hexdigest()
    resolver = _AssetResolver({("gnd_lookup_snapshot", digest): lookup})
    adapter = _CountingGnd(resolver)
    registry = MethodRegistry([_registration(adapter, logical_type="gnd_lookup_snapshot")])
    with factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="lookup-compat")
        seed_artifact(
            unit_of_work,
            project.id,
            logical_type="gnd_lookup_snapshot",
            sha256=digest,
            byte_size=lookup.stat().st_size,
            storage_uri=lookup.as_uri(),
            media_type="application/vnd.sqlite3",
        )
        snapshot = seed_ready_snapshot(
            unit_of_work, project.id, [tei_person_input(tei_id="lookup-person", gnd_id="person-1")]
        )
        run = seed_run(
            unit_of_work,
            snapshot.id,
            [MethodRunConfig(name="gnd", config={"lookup_sha256": digest})],
        )
        unit_of_work.commit()
    (scheduled,) = _scheduled(factory, registry, run.id)
    with factory() as unit_of_work:
        seed_artifact(
            unit_of_work,
            project.id,
            logical_type="gnd_lookup_snapshot",
            sha256="f" * 64,
            byte_size=10,
            media_type="application/vnd.sqlite3",
        )
        unit_of_work.commit()
    if drift:
        lookup.write_bytes(b"altered registered lookup")
        _assert_asset_rejected(factory, connection, registry, scheduled, resolver=resolver)
        assert adapter.call_count == 0
    else:
        completed = BatchExecutor(
            unit_of_work_factory=factory,
            method_registry=registry,
            worker_provenance=seed_worker_provenance(),
            lookup_asset_resolver=resolver,
            clock=lambda: NOW,
        ).execute(scheduled.message(), worker_task_id="lookup-worker", attempt_count=1)
        assert completed.status is TaskBatchStatus.completed
        assert completed.worker_provenance == seed_worker_provenance()
        assert (
            connection.execute(
                select(PredictionRow.label).where(
                    PredictionRow.method_execution_id == scheduled.method_execution_id
                )
            ).scalar_one()
            is CanonicalLabel.male
        )


@pytest.mark.parametrize("drift", ["manifest_bytes", "manifest_method", "member", "materialized"])
def test_worker_rejects_model_drift_before_adapter_compute(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
    tmp_path: Path,
    drift: str,
) -> None:
    factory, connection = postgres_unit_of_work
    member = tmp_path / "weights"
    member.write_bytes(b"small synthetic model weights")
    member_digest = hashlib.sha256(member.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    with factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="model-compat")
        member_artifact = seed_artifact(
            unit_of_work,
            project.id,
            logical_type="hf_distilbert_model_file",
            sha256=member_digest,
            byte_size=member.stat().st_size,
            storage_uri=member.as_uri(),
            media_type="application/octet-stream",
        )
        manifest = ModelManifestMetadata(
            method_name="hf_genderize" if drift == "manifest_method" else "hf_distilbert",
            model_schema_version="hf_distilbert_model_v1",
            compiler_version="hf_model_manifest_compiler_v1",
            source_identifier="synthetic/test-model",
            source_revision="fixture-v1",
            members=(
                ModelManifestMember(
                    relative_path="model.safetensors",
                    artifact_id=member_artifact.id,
                    sha256=member_digest,
                    byte_size=member.stat().st_size,
                ),
            ),
        )
        manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        seed_artifact(
            unit_of_work,
            project.id,
            logical_type="hf_distilbert_model_manifest",
            sha256=digest,
            byte_size=manifest_path.stat().st_size,
            storage_uri=manifest_path.as_uri(),
            media_type="application/json",
        )
        snapshot = seed_ready_snapshot(
            unit_of_work, project.id, [tei_person_input(tei_id="model-person", forenames=["Ada"])]
        )
        run = seed_run(
            unit_of_work,
            snapshot.id,
            [MethodRunConfig(name="hf_distilbert", config={"lookup_sha256": digest})],
        )
        unit_of_work.commit()
    resolver = _AssetResolver(
        {
            ("hf_distilbert_model_manifest", digest): manifest_path,
            ("hf_distilbert_model_file", member_digest): member,
        }
    )
    directories = RegisteredModelDirectoryResolver(
        lookup_asset_resolver=resolver, cache_root=tmp_path / "models"
    )
    adapter = _CountingDistilbert()
    registry = MethodRegistry([_registration(adapter, logical_type="hf_distilbert_model_manifest")])
    (scheduled,) = _scheduled(factory, registry, run.id)
    if drift == "manifest_bytes":
        manifest_path.write_bytes(b"changed manifest")
    elif drift == "member":
        member.write_bytes(b"changed weights")
    elif drift == "materialized":
        directory = directories.materialize_directory(
            manifest_logical_type="hf_distilbert_model_manifest",
            member_logical_type="hf_distilbert_model_file",
            manifest_sha256=digest,
            expected_method_name="hf_distilbert",
        )
        (directory / "model.safetensors").unlink()
        (directory / "model.safetensors").write_bytes(b"changed cached model")
        assert hashlib.sha256(member.read_bytes()).hexdigest() == member_digest
    _assert_asset_rejected(
        factory, connection, registry, scheduled, resolver=resolver, directory_resolver=directories
    )
    assert adapter.call_count == 0


class _FailOnceQualifier(_CountingQualifier):
    def predict_batch(
        self, people: Sequence[PersonInput], config: ParentheticalQualifierConfig
    ) -> list[PredictionResult]:
        if self.call_count == 0:
            self.call_count += 1
            raise ConnectionError("temporary infrastructure outage")
        return super().predict_batch(people, config)


def test_transient_rollback_records_only_the_eventual_completing_worker(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, connection = postgres_unit_of_work
    adapter = _FailOnceQualifier()
    registry = MethodRegistry([_registration(adapter)])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="parenthetical_qualifier")])
    (scheduled,) = _scheduled(factory, registry, run_id)
    with pytest.raises(TransientBatchError):
        _executor(factory, registry).execute(
            scheduled.message(), worker_task_id="rolled-back-attempt", attempt_count=1
        )
    with factory() as unit_of_work:
        pending = unit_of_work.runs.get_task_batch(scheduled.task_batch_id)
    assert pending is not None
    assert pending.status is TaskBatchStatus.pending
    assert pending.worker_provenance is None
    completing_worker = WorkerProvenance.model_validate(
        {
            **seed_worker_provenance().model_dump(),
            "hostname": "retry-worker",
            "process_id": 2,
        }
    )
    completed = BatchExecutor(
        unit_of_work_factory=factory,
        method_registry=registry,
        worker_provenance=completing_worker,
        clock=lambda: NOW,
    ).execute(scheduled.message(), worker_task_id="successful-attempt", attempt_count=2)
    assert completed.status is TaskBatchStatus.completed
    assert completed.worker_provenance == completing_worker
    assert completed.worker_task_id == "successful-attempt"
    assert completed.attempt_count == 2
    assert adapter.call_count == 2
    with factory() as unit_of_work:
        persisted = unit_of_work.runs.get_task_batch(scheduled.task_batch_id)
    assert persisted == completed
    assert (
        connection.execute(
            select(PredictionRow.label).where(
                PredictionRow.method_execution_id == scheduled.method_execution_id
            )
        ).scalar_one()
        is CanonicalLabel.female
    )


class _ProgressAdapter:
    descriptor = MethodDescriptor(
        name="progress_method", implementation_version="v1", normalization_version="v1"
    )
    config_model = _EmptyConfig

    def __init__(self, outcomes: tuple[PredictionStatus | None, ...]) -> None:
        self.outcomes = outcomes
        self.call_count = 0

    def predict_batch(
        self, people: Sequence[PersonInput], config: _EmptyConfig
    ) -> list[PredictionResult]:
        del config
        self.call_count += 1
        (person,) = people
        status = self.outcomes[int(person.tei_id[1:]) - 1]
        if status is None:
            raise MethodContractError("fixture permanent batch failure")
        return [
            PredictionResult(
                label=CanonicalLabel.unknown if status is PredictionStatus.success else None,
                status=status,
                raw_label=status.value,
                raw_output={"tei_id": person.tei_id},
            )
        ]


@pytest.mark.parametrize(
    ("outcomes", "fail_run", "execution_status", "run_status", "completed", "failed"),
    [
        (
            (
                PredictionStatus.success,
                PredictionStatus.abstain,
                PredictionStatus.success,
                PredictionStatus.abstain,
            ),
            False,
            MethodExecutionStatus.completed,
            RunStatus.completed,
            4,
            0,
        ),
        (
            (
                PredictionStatus.success,
                PredictionStatus.abstain,
                PredictionStatus.error,
                PredictionStatus.success,
            ),
            True,
            MethodExecutionStatus.completed_with_errors,
            RunStatus.completed_with_errors,
            3,
            1,
        ),
        (
            (
                PredictionStatus.success,
                PredictionStatus.abstain,
                None,
                PredictionStatus.error,
            ),
            True,
            MethodExecutionStatus.completed_with_errors,
            RunStatus.completed_with_errors,
            2,
            2,
        ),
        (
            (None, None, None, None),
            False,
            MethodExecutionStatus.failed,
            RunStatus.completed_with_errors,
            0,
            4,
        ),
        (
            (None, None, None, None),
            True,
            MethodExecutionStatus.failed,
            RunStatus.failed,
            0,
            4,
        ),
    ],
)
def test_each_terminal_batch_refreshes_progress_and_preserves_final_lifecycle(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
    outcomes: tuple[PredictionStatus | None, ...],
    fail_run: bool,
    execution_status: MethodExecutionStatus,
    run_status: RunStatus,
    completed: int,
    failed: int,
) -> None:
    factory, connection = postgres_unit_of_work
    adapter = _ProgressAdapter(outcomes)
    registry = MethodRegistry(
        [
            MethodRegistration(
                descriptor=adapter.descriptor,
                config_model=adapter.config_model,
                adapter=adapter,
                queue_name="cpu",
                batch_size=1,
            )
        ]
    )
    with factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="progress")
        snapshot = seed_ready_snapshot(
            unit_of_work,
            project.id,
            [tei_person_input(tei_id=f"p{index}") for index in range(1, 5)],
        )
        run = seed_run(
            unit_of_work,
            snapshot.id,
            RunConfig(
                methods=[MethodRunConfig(name=adapter.descriptor.name)],
                execution=ExecutionConfig(fail_run_on_optional_method_error=fail_run),
            ),
        )
        unit_of_work.commit()
    scheduled = _scheduled(factory, registry, run.id)
    assert len(scheduled) == 4
    executor = _executor(factory, registry)
    expected_completed = 0
    expected_failed = 0
    for index, (batch, outcome) in enumerate(zip(scheduled, outcomes, strict=True)):
        first = executor.execute(batch.message(), worker_task_id=f"first-{index}", attempt_count=1)
        expected_completed += int(outcome in {PredictionStatus.success, PredictionStatus.abstain})
        expected_failed += int(outcome is None or outcome is PredictionStatus.error)
        assert (first.success_count, first.abstain_count, first.error_count) == (
            int(outcome is PredictionStatus.success),
            int(outcome is PredictionStatus.abstain),
            int(outcome is None or outcome is PredictionStatus.error),
        )
        with factory() as unit_of_work:
            execution = unit_of_work.runs.get_method_execution(batch.method_execution_id)
            current_run = unit_of_work.runs.get_run(run.id)
        assert execution is not None
        assert execution.progress == Progress.of(
            total=4, completed=expected_completed, failed=expected_failed
        )
        assert (execution.completed_count, execution.failed_count) == (
            expected_completed,
            expected_failed,
        )
        assert current_run is not None
        assert current_run.progress == execution.progress
        terminal = index == len(scheduled) - 1
        assert execution.status is (execution_status if terminal else MethodExecutionStatus.running)
        assert current_run.status is (run_status if terminal else RunStatus.running)
        assert execution.finished_at == (NOW if terminal else None)
        assert current_run.finished_at == (NOW if terminal else None)
        duplicate = executor.execute(
            batch.message(), worker_task_id=f"duplicate-{index}", attempt_count=2
        )
        assert duplicate == first
        with factory() as unit_of_work:
            assert unit_of_work.runs.get_method_execution(execution.id) == execution
            assert unit_of_work.runs.get_run(run.id) == current_run
    assert (expected_completed, expected_failed) == (completed, failed)
    assert adapter.call_count == 4
    persisted_statuses = (
        connection.execute(
            select(PredictionRow.status).where(
                PredictionRow.method_execution_id == scheduled[0].method_execution_id
            )
        )
        .scalars()
        .all()
    )
    expected_statuses = Counter(outcome for outcome in outcomes if outcome is not None)
    assert Counter(persisted_statuses) == expected_statuses
