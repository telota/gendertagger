import pytest

from gendertagger.services.diagnostics import sanitized_diagnostic

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "postgresql+psycopg://user:credential-marker@localhost/db unavailable",
            "RuntimeError: postgresql+psycopg://<redacted>@localhost/db unavailable",
        ),
        (
            "HTTPS://user%40name:credential-marker@example.org/path and redis://token@broker/0",
            "RuntimeError: HTTPS://<redacted>@example.org/path and redis://<redacted>@broker/0",
        ),
        (
            "https://example.org/path unavailable",
            "RuntimeError: https://example.org/path unavailable",
        ),
    ],
)
def test_detailed_diagnostic_redacts_only_url_user_information(message: str, expected: str) -> None:
    assert sanitized_diagnostic(RuntimeError(message)) == expected


@pytest.mark.parametrize("length", [499, 500, 501])
def test_detailed_diagnostic_preserves_the_truncation_boundary(length: int) -> None:
    prefix = "RuntimeError: "
    message = "x" * (length - len(prefix))
    expected = prefix + message
    if length > 500:
        expected = expected[:499] + "…"
    assert sanitized_diagnostic(RuntimeError(message)) == expected


def test_url_redaction_precedes_truncation() -> None:
    credentials = "credential-marker" * 50
    diagnostic = sanitized_diagnostic(RuntimeError(f"postgresql://{credentials}@localhost/db"))
    assert diagnostic == "RuntimeError: postgresql://<redacted>@localhost/db"
