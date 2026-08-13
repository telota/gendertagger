"""Shared test configuration."""

from hypothesis import settings

settings.register_profile(
    "ci",
    deadline=None,
    derandomize=True,
    max_examples=200,
    print_blob=True,
)
settings.register_profile(
    "fuzz",
    deadline=None,
    max_examples=2_000,
    print_blob=True,
)
