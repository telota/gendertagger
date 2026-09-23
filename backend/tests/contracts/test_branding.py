import pytest
from pydantic import ValidationError

from gendertagger.models.branding import BrandingInfo, BrandingInitiative, BrandingLegalEntity


def test_branding_info_defaults_to_fully_unconfigured() -> None:
    info = BrandingInfo()

    assert info.institution_name is None
    assert info.logo_url is None
    assert info.editors == []
    assert info.published_since_year is None
    assert info.initiatives == []
    assert info.contact_email is None
    assert info.privacy_notice_url is None
    assert info.legal_entity is None


def test_branding_info_carries_configured_values() -> None:
    info = BrandingInfo(
        institution_name="Berlin-Brandenburgische Akademie der Wissenschaften",
        institution_url="https://www.bbaw.de/",
        logo_url="/api/v1/branding/logo",
        editors=["Frederike Neuber", "Lou Klappenbach", "Tim Westphal"],
        published_since_year=2026,
        initiatives=[BrandingInitiative(name="Gender & Data", url="https://gender-data.bbaw.de/")],
        contact_email="telota@bbaw.de",
        privacy_notice_url="https://www.bbaw.de/datenschutz",
        legal_entity=BrandingLegalEntity(
            name="Berlin-Brandenburgische Akademie der Wissenschaften",
            legal_form="Rechtsfähige Körperschaft des öffentlichen Rechts",
            address_lines=["Jägerstraße 22/23", "10117 Berlin"],
            telephone="+49 (0)30 20370-0",
            telephone_href="tel:+493020370-0",
            representative="Prof. Dr. Dr. h. c. mult. Christoph Markschies",
            vat_id="DE 167 449 058",
        ),
    )

    assert info.editors == ["Frederike Neuber", "Lou Klappenbach", "Tim Westphal"]
    assert info.initiatives[0].name == "Gender & Data"
    assert info.legal_entity is not None
    assert info.legal_entity.vat_id == "DE 167 449 058"


def test_branding_legal_entity_requires_a_name() -> None:
    with pytest.raises(ValidationError):
        BrandingLegalEntity(name="")


def test_branding_initiative_requires_name_and_url() -> None:
    with pytest.raises(ValidationError):
        BrandingInitiative(name="Gender & Data", url="")


def test_branding_info_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BrandingInfo.model_validate({"unexpected": "value"})


def test_branding_initiative_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BrandingInitiative.model_validate(
            {"name": "Gender & Data", "url": "https://gender-data.bbaw.de/", "unexpected": "value"}
        )


def test_branding_legal_entity_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BrandingLegalEntity.model_validate({"name": "BBAW", "unexpected": "value"})
