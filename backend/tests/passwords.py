"""Immutable synthetic credential hashes for independently constructed test records."""

from functools import cache

from gendertagger.services.password_hashing import Argon2PasswordHasher


@cache
def hash_fixture_password(password: str) -> str:
    """Hash each synthetic seed password once per process using production Argon2 parameters.

    Only the immutable hash is shared. Tests still create fresh users and sessions,
    and application login and password changes use the real password hasher.
    """
    return Argon2PasswordHasher().hash(password)
