"""Smoke tests for the installable package scaffold."""

from importlib.metadata import distribution

import gendertagger


def test_distribution_metadata_and_package_are_available() -> None:
    """Catch broken distribution metadata or src-layout installation."""
    installed_distribution = distribution("gendertagger")

    assert installed_distribution.metadata["Name"] == "gendertagger"
    assert installed_distribution.version
    assert gendertagger.__name__ == "gendertagger"
