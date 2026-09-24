from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Barrier
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy import Engine

from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.auth import AdminUserUpdate
from gendertagger.models.user import GlobalRole, UserCreate
from gendertagger.services.authentication import AuthenticationService
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.user_administration import (
    AdminUserStateConflictError,
    UserAdministrationService,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _service(factory: UnitOfWorkFactory) -> UserAdministrationService:
    return UserAdministrationService(
        unit_of_work_factory=factory,
        cursor_codec=CursorCodec(),
        authentication_service=Mock(spec=AuthenticationService),
    )


def _add_local_administrator(factory: UnitOfWorkFactory, username: str) -> UUID:
    with factory() as unit_of_work:
        user = unit_of_work.users.add_user(
            UserCreate(display_name=username, roles={GlobalRole.admin})
        )
        unit_of_work.auth.add_credential(
            user_id=user.id,
            username=username,
            password_hash="not-used-by-this-test",
        )
        unit_of_work.commit()
    return user.id


def test_concurrent_administrator_deactivations_leave_one_active_administrator(
    postgres_engine: Engine,
) -> None:
    """Serialize competing demotions on locked active-administrator user rows."""
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    first_administrator_id = _add_local_administrator(factory, "first-administrator")
    second_administrator_id = _add_local_administrator(factory, "second-administrator")
    requests_ready = Barrier(2)

    def deactivate_other(actor_user_id: UUID, target_user_id: UUID) -> str:
        requests_ready.wait(timeout=10)
        try:
            _service(factory).update_user(
                target_user_id,
                AdminUserUpdate(is_active=False),
                actor_user_id=actor_user_id,
                request_id="concurrent-admin-update",
            )
        except AdminUserStateConflictError as error:
            return error.code
        return "updated"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            future.result(timeout=15)
            for future in (
                pool.submit(
                    deactivate_other,
                    first_administrator_id,
                    second_administrator_id,
                ),
                pool.submit(
                    deactivate_other,
                    second_administrator_id,
                    first_administrator_id,
                ),
            )
        ]

    assert sorted(outcomes) == ["acting_user_not_active_administrator", "updated"]
    with factory() as unit_of_work:
        active_administrator_ids = unit_of_work.users.lock_active_administrator_ids()
    assert len(active_administrator_ids) == 1
    assert set(active_administrator_ids) <= {
        first_administrator_id,
        second_administrator_id,
    }
