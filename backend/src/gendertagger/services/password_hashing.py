"""Argon2id password hashing for local accounts (ADR-0031)."""

from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class PasswordHasherProtocol(Protocol):
    """Hash and verify plaintext passwords without exposing the underlying algorithm."""

    def hash(self, password: str) -> str:
        """Return a self-describing hash of a plaintext password."""
        ...

    def verify(self, password_hash: str, password: str) -> bool:
        """Return whether a plaintext password matches a previously hashed value."""
        ...


class Argon2PasswordHasher:
    """Argon2id hashing using the library's vetted default parameters."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash(self, password: str) -> str:
        """Return a self-describing Argon2id hash of a plaintext password."""
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        """Return whether a plaintext password matches a previously hashed value."""
        try:
            self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        return True
