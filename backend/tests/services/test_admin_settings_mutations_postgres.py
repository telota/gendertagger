"""PostgreSQL concurrency coverage for administrative settings mutations (ADR-0040)."""

from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import Engine, insert

from gendertagger.db.rows.settings import DeploymentSettingsRow
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.admin_settings import (
    AdminSettingsReset,
    AdminSettingsUpdate,
    BrandingEditableValues,
    BrandingOverrides,
    BrandingSettingField,
)
from gendertagger.models.branding import BrandingInfo
from gendertagger.services.admin_settings import (
    AdminSettingsService,
    SettingsRevisionConflictError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")


def _service(factory: UnitOfWorkFactory) -> AdminSettingsService:
    return AdminSettingsService(
        unit_of_work_factory=factory,
        branding_defaults=BrandingEditableValues(
            institution_name="Environment Institute",
            institution_url=None,
            contact_email="environment@example.org",
            privacy_notice_url=None,
            editors=[],
            published_since_year=None,
        ),
        deployment_branding=BrandingInfo(),
    )


def _seed_settings(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(DeploymentSettingsRow).values(
                id=1,
                revision=0,
                branding_overrides={"contact_email": "stored@example.org"},
            )
        )


@pytest.mark.parametrize("competing_operation", ["update", "reset"])
def test_concurrent_settings_mutations_preserve_one_winner_and_one_stale_conflict(
    postgres_engine: Engine,
    competing_operation: str,
) -> None:
    _seed_settings(postgres_engine)
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    requests_ready = Barrier(2)

    def mutate(index: int) -> str:
        requests_ready.wait(timeout=10)
        service = _service(factory)
        try:
            if competing_operation == "reset" and index == 1:
                service.reset_settings(
                    AdminSettingsReset(
                        expected_revision=0,
                        fields=[BrandingSettingField.contact_email],
                    ),
                    actor_user_id=ACTOR_ID,
                    request_id="concurrent-settings-reset",
                )
            else:
                service.update_settings(
                    AdminSettingsUpdate(
                        expected_revision=0,
                        branding=BrandingOverrides(institution_name=f"Institute {index}"),
                    ),
                    actor_user_id=ACTOR_ID,
                    request_id="concurrent-settings-update",
                )
        except SettingsRevisionConflictError:
            return "conflict"
        return "updated"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            future.result(timeout=15) for future in (pool.submit(mutate, 0), pool.submit(mutate, 1))
        ]

    assert sorted(outcomes) == ["conflict", "updated"]
    with factory() as unit_of_work:
        resulting = unit_of_work.settings.get_deployment_settings()
    assert resulting is not None
    assert resulting.revision == 1
