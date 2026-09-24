"""Contract coverage for administrative branding settings (ADR-0040)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from gendertagger.models.admin_settings import (
    AdminSettingsReset,
    AdminSettingsUpdate,
    BrandingEditableValues,
    BrandingOverrides,
    BrandingSettingField,
)


def test_branding_overrides_distinguish_omission_null_and_empty_editor_list() -> None:
    omitted = BrandingOverrides()
    cleared_email = BrandingOverrides(contact_email=None)
    cleared_editors = BrandingOverrides(editors=[])

    assert omitted.model_dump(exclude_unset=True) == {}
    assert cleared_email.model_dump(exclude_unset=True) == {"contact_email": None}
    assert cleared_editors.model_dump(exclude_unset=True) == {"editors": []}
    assert omitted.model_fields_set == set()
    assert cleared_email.model_fields_set == {"contact_email"}
    assert cleared_editors.model_fields_set == {"editors"}


def test_branding_overrides_reject_unknown_fields_and_null_editors() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BrandingOverrides.model_validate({"unapproved": "value"})
    with pytest.raises(ValidationError):
        BrandingOverrides.model_validate({"editors": None})


def test_branding_editable_values_retains_existing_environment_value_shapes() -> None:
    values = BrandingEditableValues(
        institution_name="  Existing deployment value  ",
        institution_url="not-validated-yet",
        contact_email="not-validated-yet",
        privacy_notice_url="not-validated-yet",
        editors=["", "duplicate", "duplicate"],
        published_since_year=0,
    )

    assert values.editors == ["", "duplicate", "duplicate"]
    assert values.published_since_year == 0


def test_branding_field_allowlist_is_exact() -> None:
    assert list(BrandingSettingField) == [
        BrandingSettingField.institution_name,
        BrandingSettingField.institution_url,
        BrandingSettingField.contact_email,
        BrandingSettingField.privacy_notice_url,
        BrandingSettingField.editors,
        BrandingSettingField.published_since_year,
    ]


def test_branding_overrides_apply_administrative_write_validation() -> None:
    overrides = BrandingOverrides(
        institution_name="  Example Institute  ",
        institution_url="https://example.org/publisher",
        contact_email="contact@example.org",
        privacy_notice_url="/privacy",
        editors=["  First Editor ", "Second Editor"],
        published_since_year=2024,
    )

    assert overrides.institution_name == "Example Institute"
    assert overrides.editors == ["First Editor", "Second Editor"]


@pytest.mark.parametrize(
    "payload",
    [
        {"institution_name": " \n"},
        {"institution_url": "ftp://example.org"},
        {"institution_url": "https://user:secret@example.org"},
        {"institution_url": "//other.example/privacy"},
        {"privacy_notice_url": "/bad\\path"},
        {"contact_email": "Display <contact@example.org>"},
        {"contact_email": "mailto:contact@example.org"},
        {"contact_email": "contact@example.org?subject=hello"},
        {"editors": ["Editor", " Editor "]},
        {"published_since_year": True},
        {"published_since_year": "2024"},
        {"published_since_year": 0},
        {"published_since_year": datetime.now(UTC).year + 1},
    ],
)
def test_branding_overrides_reject_invalid_administrative_write_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        BrandingOverrides.model_validate(payload)


def test_update_and_reset_contracts_require_nonempty_closed_commands() -> None:
    update = AdminSettingsUpdate(
        expected_revision=0,
        branding=BrandingOverrides(contact_email=None),
    )
    reset = AdminSettingsReset(
        expected_revision=0,
        fields=[BrandingSettingField.contact_email],
    )

    assert update.branding.model_fields_set == {"contact_email"}
    assert reset.fields == [BrandingSettingField.contact_email]
    with pytest.raises(ValidationError):
        AdminSettingsUpdate.model_validate({"expected_revision": 0, "branding": {}})
    with pytest.raises(ValidationError):
        AdminSettingsReset.model_validate(
            {
                "expected_revision": 0,
                "fields": ["contact_email", "contact_email"],
            }
        )
