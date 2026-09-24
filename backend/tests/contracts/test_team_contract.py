from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from gendertagger.models.project import ProjectCreate
from gendertagger.models.team import TeamCreate, TeamMember, TeamMemberAdd, TeamSummary, TeamUpdate

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
TEAM_ID = UUID("20000000-0000-0000-0000-000000000001")
USER_ID = UUID("20000000-0000-0000-0000-000000000002")


@pytest.mark.contract
def test_team_create_normalizes_slug_without_rewriting_display_name() -> None:
    command = TeamCreate(slug="  Editorial-Group  ", display_name="  Editorial group  ")

    assert command.slug == "editorial-group"
    assert command.display_name == "  Editorial group  "


@pytest.mark.contract
@pytest.mark.parametrize("slug", ["", "1-team", "team--group", "team_group", "x" * 101])
def test_team_create_rejects_invalid_canonical_slug(slug: str) -> None:
    with pytest.raises(ValidationError):
        TeamCreate(slug=slug, display_name="Team")


@pytest.mark.contract
@pytest.mark.parametrize(
    "payload", [{"display_name": None}, {"display_name": "   "}, {"slug": "new"}]
)
def test_team_update_rejects_null_blank_and_immutable_slug(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TeamUpdate.model_validate(payload)


@pytest.mark.contract
def test_team_update_allows_an_omitted_display_name_for_idempotent_patch_semantics() -> None:
    assert TeamUpdate().model_fields_set == set()


@pytest.mark.contract
def test_team_read_contracts_are_frozen_and_roster_free() -> None:
    summary = TeamSummary(
        id=TEAM_ID,
        slug="editorial-group",
        display_name="Editorial group",
        created_at=NOW,
        updated_at=NOW,
    )
    member = TeamMember(
        team_id=TEAM_ID,
        user_id=USER_ID,
        display_name="Member",
        is_active=True,
        created_at=NOW,
    )

    assert "member_count" not in summary.model_dump()
    with pytest.raises(ValidationError):
        TeamMemberAdd.model_validate({})
    with pytest.raises(ValidationError):
        summary.display_name = "Renamed"
    assert member.user_id == USER_ID


@pytest.mark.contract
def test_team_slice_preserves_the_existing_unscoped_project_create_contract() -> None:
    project = ProjectCreate(slug="existing-project", display_name="Existing project")

    assert "team_id" not in project.model_dump()
