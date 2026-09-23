from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from gendertagger.cli.main import _build_parser, _download_https, main
from gendertagger.db.repositories.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.repositories.auth_repository import SqlAlchemyAuthRepository
from gendertagger.db.repositories.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
from gendertagger.models.artifact import LookupArtifactMetadata
from gendertagger.models.project import ProjectCreate
from gendertagger.models.user import GlobalRole
from gendertagger.services.password_hashing import Argon2PasswordHasher
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.storage.local import LocalArtifactStorage


def test_asset_download_rejects_non_https_urls(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute HTTPS"):
        _download_https(
            "http://example.test/NamesOut.txt",
            tmp_path / "download",
            expected_sha256="a" * 64,
            max_byte_size=1024,
        )


def test_build_gnd_cli_accepts_multiple_dnb_entity_dumps() -> None:
    args = _build_parser().parse_args(
        ["assets", "build-gnd", "person.xml.gz", "corporate-body.xml.gz"]
    )

    assert args.sources == [Path("person.xml.gz"), Path("corporate-body.xml.gz")]


def test_fetch_gnd_cli_pairs_each_url_with_a_checksum() -> None:
    args = _build_parser().parse_args(
        [
            "assets",
            "fetch-gnd",
            "https://data.example/person.xml.gz",
            "https://data.example/corporate.xml.gz",
            "--expected-sha256",
            "a" * 64,
            "--expected-sha256",
            "b" * 64,
        ]
    )

    assert args.urls == [
        "https://data.example/person.xml.gz",
        "https://data.example/corporate.xml.gz",
    ]
    assert args.expected_sha256 == ["a" * 64, "b" * 64]


@pytest.mark.postgres
def test_prepare_wiki_cli_registers_source_and_compiled_lookup(
    repository_database_url: str,
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    database_url = make_url(repository_database_url).set(drivername="postgresql+psycopg")
    monkeypatch.setenv(
        "GENDERTAGGER_DATABASE_URL",
        database_url.render_as_string(hide_password=False),
    )
    monkeypatch.setenv("GENDERTAGGER_ARTIFACT_ROOT", str(artifact_root))
    source = tmp_path / "NamesOut.txt"
    source_bytes = b"Karl\tM\nMaria\tF\n"
    source.write_bytes(source_bytes)

    exit_code = main(
        [
            "assets",
            "prepare-wiki",
            str(source),
            "--source-version",
            "wiki-gendersort-test",
            "--source-url",
            "https://example.test/NamesOut.txt",
            "--license-identifier",
            "test-license",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    [source_payload] = payload["source_artifacts"]
    assert source_payload["sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert payload["lookup_logical_type"] == "wiki_gendersort_lookup"

    with Session(postgres_engine) as session:
        artifacts = SqlAlchemyArtifactRepository(session)
        source_artifact = artifacts.get_artifact(UUID(source_payload["artifact_id"]))
        lookup_artifact = artifacts.get_artifact(UUID(payload["lookup_artifact_id"]))

    assert source_artifact is not None
    assert source_artifact.metadata == {
        "license_identifier": "test-license",
        "source_url": "https://example.test/NamesOut.txt",
        "source_version": "wiki-gendersort-test",
    }
    assert lookup_artifact is not None
    metadata = LookupArtifactMetadata.model_validate(lookup_artifact.metadata)
    assert metadata.method_name == "wiki_gendersort"
    assert len(metadata.source_artifacts) == 1
    assert metadata.source_artifacts[0].artifact_id == source_artifact.id
    assert metadata.source_artifacts[0].sha256 == source_artifact.sha256
    assert metadata.source_version == "wiki-gendersort-test"
    assert metadata.record_count == 2

    lookup_path = LocalArtifactStorage(artifact_root).materialize(lookup_artifact.storage_uri)
    uri = f"{lookup_path.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        rows = connection.execute(
            "SELECT name, native_label FROM wiki_names ORDER BY name"
        ).fetchall()
    finally:
        connection.close()
    assert rows == [("Karl", "M"), ("Maria", "F")]


def test_users_create_cli_collects_repeated_global_roles() -> None:
    args = _build_parser().parse_args(
        [
            "users",
            "create",
            "--display-name",
            "Admin One",
            "--username",
            "admin.one",
            "--role",
            "operator",
            "--role",
            "admin",
        ]
    )

    assert args.display_name == "Admin One"
    assert args.username == "admin.one"
    assert args.roles == ["operator", "admin"]
    assert args.password is None


def test_users_create_cli_makes_global_roles_optional_and_rejects_project_roles() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        ["users", "create", "--display-name", "Reviewer One", "--username", "reviewer.one"]
    )

    assert args.roles == []
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "users",
                "create",
                "--display-name",
                "Reviewer One",
                "--username",
                "reviewer.one",
                "--role",
                "reviewer",
            ]
        )


def test_users_reset_password_cli_parses_user_id() -> None:
    user_id = UUID("d0000000-0000-0000-0000-000000000001")

    args = _build_parser().parse_args(
        ["users", "reset-password", "--user-id", str(user_id), "--password", "a-supplied-pass-99"]
    )

    assert args.user_id == user_id
    assert args.password == "a-supplied-pass-99"


@pytest.mark.postgres
def test_users_create_cli_provisions_local_account_with_generated_password(
    repository_database_url: str,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = make_url(repository_database_url).set(drivername="postgresql+psycopg")
    monkeypatch.setenv(
        "GENDERTAGGER_DATABASE_URL", database_url.render_as_string(hide_password=False)
    )

    exit_code = main(
        [
            "users",
            "create",
            "--display-name",
            "Reviewer One",
            "--username",
            "Reviewer.One",
            "--role",
            "operator",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["username"] == "reviewer.one"
    assert len(payload["generated_password"]) >= 12

    with Session(postgres_engine) as session:
        credential = SqlAlchemyAuthRepository(session).get_credential_by_username("reviewer.one")
        assert credential is not None
        user = SqlAlchemyUserRepository(session).get_user(credential.user_id)

    assert credential.must_change_password is True
    assert Argon2PasswordHasher().verify(credential.password_hash, payload["generated_password"])
    assert user is not None
    assert user.roles == {GlobalRole.operator}
    assert str(user.id) == payload["user_id"]


@pytest.mark.postgres
def test_users_reset_password_cli_forces_change_and_revokes_sessions(
    repository_database_url: str,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = make_url(repository_database_url).set(drivername="postgresql+psycopg")
    monkeypatch.setenv(
        "GENDERTAGGER_DATABASE_URL", database_url.render_as_string(hide_password=False)
    )
    main(
        [
            "users",
            "create",
            "--display-name",
            "Reviewer Two",
            "--username",
            "reviewer.two",
            "--password",
            "an-original-passphrase-1",
        ]
    )
    created = json.loads(capsys.readouterr().out)
    with Session(postgres_engine) as session:
        auth_repository = SqlAlchemyAuthRepository(session)
        auth_repository.create_session(
            session_id="a" * 64,
            user_id=UUID(created["user_id"]),
            csrf_secret="csrf-secret",
            keep_signed_in=False,
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            absolute_expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        )
        session.commit()

    exit_code = main(
        [
            "users",
            "reset-password",
            "--user-id",
            created["user_id"],
            "--password",
            "a-forced-new-passphrase-2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"user_id": created["user_id"]}

    with Session(postgres_engine) as session:
        auth_repository = SqlAlchemyAuthRepository(session)
        credential = auth_repository.get_credential(UUID(created["user_id"]))
        assert credential is not None
        active_session = auth_repository.get_session("a" * 64)

    assert credential.must_change_password is True
    assert Argon2PasswordHasher().verify(credential.password_hash, "a-forced-new-passphrase-2")
    assert active_session is not None
    assert active_session.revoked_at is not None


@pytest.mark.postgres
def test_projects_cli_grants_changes_lists_and_revokes_membership(
    repository_database_url: str,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = make_url(repository_database_url).set(drivername="postgresql+psycopg")
    monkeypatch.setenv(
        "GENDERTAGGER_DATABASE_URL", database_url.render_as_string(hide_password=False)
    )
    with Session(postgres_engine) as session:
        project = SqlAlchemyProjectRepository(session).add_project(
            ProjectCreate(slug="cli-membership", display_name="CLI membership")
        )
        session.commit()
    main(["users", "create", "--display-name", "Member One", "--username", "member.one"])
    user_id = json.loads(capsys.readouterr().out)["user_id"]
    membership = ["--project", "cli-membership", "--username", "Member.One"]

    main(["projects", "add-member", *membership, "--role", "viewer"])
    granted = json.loads(capsys.readouterr().out)
    main(["projects", "add-member", *membership, "--role", "reviewer"])
    changed = json.loads(capsys.readouterr().out)
    main(["projects", "list-members", "--project", "cli-membership"])
    listed = json.loads(capsys.readouterr().out)
    main(["projects", "remove-member", *membership])
    removed = json.loads(capsys.readouterr().out)
    main(["projects", "list-members", "--project", "cli-membership"])
    listed_after_removal = json.loads(capsys.readouterr().out)

    assert (granted["user_id"], granted["role"]) == (user_id, "viewer")
    assert changed["role"] == "reviewer"
    assert [(member["display_name"], member["role"]) for member in listed] == [
        ("Member One", "reviewer")
    ]
    assert removed == {"project_id": str(project.id), "user_id": user_id}
    assert listed_after_removal == []


@pytest.mark.postgres
def test_projects_cli_rejects_unknown_projects_users_and_memberships(
    repository_database_url: str,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = make_url(repository_database_url).set(drivername="postgresql+psycopg")
    monkeypatch.setenv(
        "GENDERTAGGER_DATABASE_URL", database_url.render_as_string(hide_password=False)
    )
    with Session(postgres_engine) as session:
        SqlAlchemyProjectRepository(session).add_project(
            ProjectCreate(slug="cli-unknowns", display_name="CLI unknowns")
        )
        session.commit()
    main(["users", "create", "--display-name", "Outsider", "--username", "outsider"])
    capsys.readouterr()

    with pytest.raises(ValueError, match="project 'missing' does not exist"):
        main(["projects", "list-members", "--project", "missing"])
    with pytest.raises(ValueError, match="user 'nobody' does not exist"):
        main(
            [
                "projects",
                "add-member",
                "--project",
                "cli-unknowns",
                "--username",
                "nobody",
                "--role",
                "viewer",
            ]
        )
    with pytest.raises(ResourceNotFoundError, match="is not a member"):
        main(["projects", "remove-member", "--project", "cli-unknowns", "--username", "outsider"])
