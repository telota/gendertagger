import json
from typing import cast
from unittest.mock import Mock

import pytest

from gendertagger.cli import teams
from gendertagger.cli.main import _build_parser
from gendertagger.config.settings import DatabaseSettings

pytestmark = pytest.mark.unit


def test_teams_cli_parses_immutable_slug_rename_and_roster_commands() -> None:
    parser = _build_parser()

    create = parser.parse_args(
        ["teams", "create", "--slug", "editorial-group", "--display-name", "Editorial group"]
    )
    rename = parser.parse_args(
        ["teams", "rename", "--team", "editorial-group", "--display-name", "Renamed group"]
    )
    add_member = parser.parse_args(
        ["teams", "add-member", "--team", "editorial-group", "--username", "member.one"]
    )

    assert create.team_command == "create"
    assert rename.team == "editorial-group"
    assert add_member.username == "member.one"


def test_teams_cli_lists_through_the_team_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock()
    service.list_admin_teams.return_value = Mock(model_dump=lambda **_: {"items": []})
    engine = Mock()
    monkeypatch.setattr(teams, "create_database_engine", lambda _: engine)
    monkeypatch.setattr(teams, "create_session_factory", lambda _: Mock())
    monkeypatch.setattr(teams, "TeamService", lambda **_: service)
    args = _build_parser().parse_args(["teams", "list", "--query", "editorial"])

    settings = cast(
        DatabaseSettings,
        Mock(database_url=Mock(get_secret_value=lambda: "postgresql://test")),
    )
    payload = teams.run(args, settings)

    assert json.loads(payload) == {"items": []}
    service.list_admin_teams.assert_called_once_with(query="editorial", limit=100, cursor=None)
    engine.dispose.assert_called_once_with()
