"""Newest-first list use cases for snapshots, runs, aggregations, evaluations, and exports."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast
from unittest.mock import Mock, call
from uuid import UUID

import pytest

from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.api import CursorPage
from gendertagger.services.aggregation_repository import AggregationRepository
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.evaluation_repository import EvaluationRepository
from gendertagger.services.evaluations import EvaluationService
from gendertagger.services.export_repository import ExportRepository
from gendertagger.services.exports import ExportService
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.pagination import CreationPosition, CursorCodec
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.project_repository import ProjectRepository
from gendertagger.services.projects import ProjectService
from gendertagger.services.run_repository import RunRepository
from gendertagger.services.runs import RunProvenance, RunService
from gendertagger.services.unit_of_work import UnitOfWork
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
PARENT_ID = UUID("10000000-0000-0000-0000-000000000001")
CASES = ("snapshots", "runs", "aggregations", "evaluations", "exports")


@dataclass(frozen=True)
class _Listed:
    id: UUID
    created_at: datetime


LISTED = tuple(
    _Listed(
        id=UUID(f"20000000-0000-0000-0000-00000000000{index}"),
        created_at=NOW - timedelta(minutes=index),
    )
    for index in range(1, 4)
)


class _ListingUnitOfWork:
    """Expose every repository a list use case reads, without persistence."""

    def __init__(self) -> None:
        self.projects = Mock(spec=ProjectRepository)
        self.runs = Mock(spec=RunRepository)
        self.aggregations = Mock(spec=AggregationRepository)
        self.evaluations = Mock(spec=EvaluationRepository)
        self.exports = Mock(spec=ExportRepository)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def factory(self) -> UnitOfWork:
        return cast(UnitOfWork, self)


@dataclass(frozen=True)
class _ListCase:
    """One list use case with the parent lookup and repository slice it depends on."""

    list_page: Callable[..., CursorPage[Any]]
    parent_lookup: Mock
    repository_slice: Mock


def _list_case(name: str, unit_of_work: _ListingUnitOfWork, tmp_path: Path) -> _ListCase:
    codec = CursorCodec()
    storage = LocalArtifactStorage(tmp_path)
    if name == "snapshots":
        projects = ProjectService(
            unit_of_work_factory=unit_of_work.factory,
            artifact_storage=storage,
            parser=TeiPersonParser(),
            cursor_codec=codec,
            clock=lambda: NOW,
            max_upload_bytes=1,
        )
        return _ListCase(
            projects.list_snapshots,
            unit_of_work.projects.get_project,
            unit_of_work.projects.list_snapshots,
        )
    if name == "runs":
        runs = RunService(
            unit_of_work_factory=unit_of_work.factory,
            method_registry=MethodRegistry([]),
            provenance=RunProvenance(
                code_git_commit="c" * 40,
                application_version="0.0.0",
                python_version="3.13.14",
                dependency_lock_sha256="d" * 64,
            ),
            cursor_codec=codec,
        )
        return _ListCase(
            runs.list_runs,
            unit_of_work.projects.get_snapshot,
            unit_of_work.runs.list_runs,
        )
    if name == "aggregations":
        aggregations = AggregationService(
            unit_of_work_factory=unit_of_work.factory,
            cursor_codec=codec,
            clock=lambda: NOW,
        )
        return _ListCase(
            aggregations.list_aggregations,
            unit_of_work.runs.get_run,
            unit_of_work.aggregations.list_aggregations,
        )
    if name == "evaluations":
        evaluations = EvaluationService(
            unit_of_work_factory=unit_of_work.factory,
            artifact_storage=storage,
            cursor_codec=codec,
            clock=lambda: NOW,
        )
        return _ListCase(
            evaluations.list_evaluations,
            unit_of_work.runs.get_run,
            unit_of_work.evaluations.list_evaluations,
        )
    exports = ExportService(
        unit_of_work_factory=unit_of_work.factory,
        artifact_storage=storage,
        cursor_codec=codec,
        clock=lambda: NOW,
    )
    return _ListCase(
        exports.list_exports,
        unit_of_work.runs.get_run,
        unit_of_work.exports.list_exports,
    )


@pytest.mark.parametrize("name", CASES)
def test_list_use_case_pages_newest_first_under_an_existing_parent(
    name: str,
    tmp_path: Path,
) -> None:
    unit_of_work = _ListingUnitOfWork()
    case = _list_case(name, unit_of_work, tmp_path)
    case.repository_slice.side_effect = [list(LISTED), [LISTED[2]]]

    first_page = case.list_page(PARENT_ID, limit=2, cursor=None)
    second_page = case.list_page(PARENT_ID, limit=2, cursor=first_page.next_cursor)

    assert first_page.items == list(LISTED[:2])
    assert first_page.has_more is True
    assert second_page.items == [LISTED[2]]
    assert second_page.has_more is False
    assert case.repository_slice.call_args_list == [
        call(PARENT_ID, limit=3, after=None),
        call(
            PARENT_ID,
            limit=3,
            after=CreationPosition(created_at=LISTED[1].created_at, id=LISTED[1].id),
        ),
    ]


@pytest.mark.parametrize("name", CASES)
def test_list_use_case_rejects_a_missing_parent_and_a_nonpositive_limit(
    name: str,
    tmp_path: Path,
) -> None:
    unit_of_work = _ListingUnitOfWork()
    case = _list_case(name, unit_of_work, tmp_path)
    case.parent_lookup.return_value = None

    with pytest.raises(ResourceNotFoundError, match=str(PARENT_ID)):
        case.list_page(PARENT_ID, limit=2, cursor=None)
    with pytest.raises(ValueError, match="limit must be positive"):
        case.list_page(PARENT_ID, limit=0, cursor=None)
    case.repository_slice.assert_not_called()
