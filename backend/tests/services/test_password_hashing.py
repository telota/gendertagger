from gendertagger.services.password_hashing import Argon2PasswordHasher


def test_argon2_password_hasher_round_trips_a_matching_password() -> None:
    hasher = Argon2PasswordHasher()

    password_hash = hasher.hash("a-correct-passphrase")

    assert hasher.verify(password_hash, "a-correct-passphrase") is True


def test_argon2_password_hasher_rejects_a_wrong_password() -> None:
    hasher = Argon2PasswordHasher()

    password_hash = hasher.hash("a-correct-passphrase")

    assert hasher.verify(password_hash, "a-different-passphrase") is False


def test_argon2_password_hasher_rejects_a_malformed_hash() -> None:
    hasher = Argon2PasswordHasher()

    assert hasher.verify("not-an-argon2-hash", "a-correct-passphrase") is False


def test_argon2_password_hasher_salts_each_hash_differently() -> None:
    hasher = Argon2PasswordHasher()

    first_hash = hasher.hash("a-correct-passphrase")
    second_hash = hasher.hash("a-correct-passphrase")

    assert first_hash != second_hash
    assert hasher.verify(first_hash, "a-correct-passphrase") is True
    assert hasher.verify(second_hash, "a-correct-passphrase") is True
