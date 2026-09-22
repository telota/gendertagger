"""End-to-end tests for the public branding resource (ADR-0036)."""

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.settings import AppSettings, BrandingSettings
from gendertagger.models.branding import BrandingInitiative, BrandingLegalEntity
from gendertagger.services.unit_of_work import UnitOfWork

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("The branding resource must not open persistence")


def _client(*, branding: BrandingSettings | None = None) -> TestClient:
    settings = AppSettings(
        database_url=SecretStr(DATABASE_URL),
        code_git_commit=CODE_GIT_COMMIT,
        dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        branding=branding or BrandingSettings(),
    )
    application = create_app(settings=settings, unit_of_work_factory=_unused_unit_of_work_factory)
    return TestClient(application)


def test_unconfigured_deployment_reports_every_field_as_absent() -> None:
    response = _client().get("/api/v1/branding")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "institution_name": None,
        "institution_url": None,
        "logo_url": None,
        "editors": [],
        "published_since_year": None,
        "initiatives": [],
        "contact_email": None,
        "privacy_notice_url": None,
        "legal_entity": None,
    }


def test_configured_deployment_reports_its_values(tmp_path: Path) -> None:
    logo_path = tmp_path / "logo.svg"
    logo_path.write_text("<svg></svg>", encoding="utf-8")
    branding = BrandingSettings(
        institution_name="Berlin-Brandenburgische Akademie der Wissenschaften",
        institution_url="https://www.bbaw.de/",
        logo_path=logo_path,
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

    response = _client(branding=branding).get("/api/v1/branding")

    assert response.status_code == 200
    body = response.json()
    assert body["institution_name"] == "Berlin-Brandenburgische Akademie der Wissenschaften"
    assert body["logo_url"] == "/api/v1/branding/logo"
    assert body["editors"] == ["Frederike Neuber", "Lou Klappenbach", "Tim Westphal"]
    assert body["initiatives"] == [{"name": "Gender & Data", "url": "https://gender-data.bbaw.de/"}]
    assert body["legal_entity"]["vat_id"] == "DE 167 449 058"


def test_branding_needs_no_session_and_no_csrf_token() -> None:
    response = _client().get("/api/v1/branding")

    assert response.status_code == 200


def test_logo_is_404_when_unconfigured() -> None:
    response = _client().get("/api/v1/branding/logo")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_logo_is_404_when_the_configured_file_is_missing(tmp_path: Path) -> None:
    branding = BrandingSettings(logo_path=tmp_path / "missing.svg")

    response = _client(branding=branding).get("/api/v1/branding/logo")

    assert response.status_code == 404


def test_logo_streams_the_configured_file_with_its_media_type(tmp_path: Path) -> None:
    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(b"\x89PNG\r\n\x1a\n-fake-")
    branding = BrandingSettings(logo_path=logo_path)

    response = _client(branding=branding).get("/api/v1/branding/logo")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == logo_path.read_bytes()


def test_logo_falls_back_to_a_generic_media_type_for_an_unrecognised_extension(
    tmp_path: Path,
) -> None:
    logo_path = tmp_path / "logo.unknownext"
    logo_path.write_bytes(b"opaque-bytes")
    branding = BrandingSettings(logo_path=logo_path)

    response = _client(branding=branding).get("/api/v1/branding/logo")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
