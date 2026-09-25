"""Closed presentation-preference contracts and explicit patch semantics (ADR-0043)."""

import pytest
from pydantic import ValidationError

from gendertagger.models.user_preferences import UserPreferences, UserPreferencesUpdate

pytestmark = pytest.mark.contract


def test_preferences_defaults_preserve_unresolved_browser_choices() -> None:
    assert UserPreferences().model_dump(mode="json") == {
        "locale": None,
        "theme": "system",
        "desktop_sidebar_collapsed": False,
        "revision": 0,
    }


@pytest.mark.parametrize("locale", ["de", "en", None])
@pytest.mark.parametrize("theme", ["system", "light", "dark"])
def test_preferences_accept_only_documented_language_and_theme_choices(
    locale: str | None,
    theme: str,
) -> None:
    payload = {"locale": locale, "theme": theme, "desktop_sidebar_collapsed": True}

    resource = UserPreferences.model_validate(payload)
    command = UserPreferencesUpdate.model_validate({"expected_revision": 0, **payload})

    assert resource.model_dump(exclude={"revision"}) == payload
    assert command.model_dump(exclude={"expected_revision"}, exclude_unset=True) == payload


@pytest.mark.parametrize(
    "preference",
    [{"theme": "dark"}, {"desktop_sidebar_collapsed": True}, {"locale": None}],
)
def test_preferences_update_distinguishes_omission_from_explicit_values(
    preference: dict[str, object],
) -> None:
    payload = {"expected_revision": 2, **preference}

    command = UserPreferencesUpdate.model_validate(payload)

    assert command.model_fields_set == set(payload)
    assert command.model_dump(exclude_unset=True) == payload


def test_preferences_update_schema_requires_revision_without_preference_defaults() -> None:
    schema = UserPreferencesUpdate.model_json_schema()

    assert schema["required"] == ["expected_revision"]
    for field_name in ("locale", "theme", "desktop_sidebar_collapsed"):
        assert "default" not in schema["properties"][field_name]


@pytest.mark.parametrize(
    "payload",
    [
        {"locale": "fr"},
        {"locale": "DE"},
        {"locale": "de-DE"},
        {"locale": "browser"},
        {"locale": ""},
        {"theme": None},
        {"theme": "auto"},
        {"theme": "DARK"},
        {"desktop_sidebar_collapsed": None},
        {"desktop_sidebar_collapsed": "false"},
        {"desktop_sidebar_collapsed": 0},
        {"desktop_sidebar_collapsed": 1},
        {"user_id": "another-account"},
        {"project_id": "another-project"},
        {"settings": {"locale": "en"}},
    ],
)
def test_preferences_resource_and_update_reject_invalid_or_unknown_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        UserPreferences.model_validate(payload)
    with pytest.raises(ValidationError):
        UserPreferencesUpdate.model_validate({"expected_revision": 0, **payload})


@pytest.mark.parametrize("revision", [-1, True, False, "0", 0.0, None])
def test_preferences_revisions_are_strict_nonnegative_integers(revision: object) -> None:
    with pytest.raises(ValidationError):
        UserPreferences.model_validate({"revision": revision})
    with pytest.raises(ValidationError):
        UserPreferencesUpdate.model_validate({"expected_revision": revision, "locale": "de"})


@pytest.mark.parametrize("payload", [{}, {"expected_revision": 0}, {"theme": "dark"}])
def test_preferences_update_requires_revision_and_at_least_one_preference(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        UserPreferencesUpdate.model_validate(payload)
