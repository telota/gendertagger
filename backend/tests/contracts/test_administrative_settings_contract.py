"""Contract coverage for administrative branding settings (ADR-0040)."""

import pytest
from pydantic import ValidationError

from gendertagger.models.admin_settings import (
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
