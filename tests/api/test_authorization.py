from uuid import UUID

import pytest

from gendertagger.api.authorization import has_role
from gendertagger.models.user import CurrentUser, Role


def _user(role: Role) -> CurrentUser:
    return CurrentUser(
        id=UUID("a2f03480-77a7-4f24-82cb-07604d5c2483"),
        display_name="Role fixture",
        roles={role},
    )


@pytest.mark.parametrize(
    ("assigned_role", "required_role", "is_authorized"),
    [
        (Role.viewer, Role.viewer, True),
        (Role.viewer, Role.reviewer, False),
        (Role.reviewer, Role.viewer, True),
        (Role.reviewer, Role.operator, False),
        (Role.operator, Role.viewer, True),
        (Role.operator, Role.reviewer, True),
        (Role.operator, Role.operator, True),
        (Role.admin, Role.viewer, True),
        (Role.admin, Role.operator, True),
        (Role.admin, Role.admin, True),
    ],
)
def test_roles_grant_hierarchical_capabilities(
    assigned_role: Role,
    required_role: Role,
    is_authorized: bool,
) -> None:
    assert has_role(_user(assigned_role), required_role) is is_authorized
