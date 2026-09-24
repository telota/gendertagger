"""Administrator-facing local-account queries (ADR-0039)."""

import hashlib
import logging
import secrets
from uuid import UUID

from gendertagger.models.api import CursorPage
from gendertagger.models.auth import (
    AdminUser,
    AdminUserCreate,
    AdminUserCreateResult,
    normalize_username,
)
from gendertagger.services.authentication import AuthenticationService
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.ports.auth_repository import AdminUserCursor
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

_USER_DIRECTORY_RESOURCE = "admin_users"
logger = logging.getLogger(__name__)


class UserAdministrationService:
    """Query local accounts without exposing credentials or persistence models."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        cursor_codec: CursorCodec,
        authentication_service: AuthenticationService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._cursor_codec = cursor_codec
        self._authentication_service = authentication_service

    def list_users(
        self,
        *,
        query: str | None,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[AdminUser]:
        """Return one filtered, username-ordered page of local accounts."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        normalized_query = _normalize_query(query)
        resource = _resource_for_query(normalized_query)
        position = (
            self._cursor_codec.decode(cursor, expected_resource=resource)
            if cursor is not None
            else None
        )
        after = None
        if position is not None:
            try:
                username = normalize_username(position.sort_values[0])
            except ValueError as error:
                raise InvalidCursorError("cursor username is invalid") from error
            after = AdminUserCursor(username=username, user_id=position.id)
        with self._unit_of_work_factory() as unit_of_work:
            users = unit_of_work.auth.list_admin_users(
                search=normalized_query,
                limit=limit + 1,
                after=after,
            )
        has_more = len(users) > limit
        items = list(users[:limit])
        next_cursor = None
        if has_more:
            last_item = items[-1]
            next_cursor = self._cursor_codec.encode(
                resource=resource,
                sort_values=(last_item.username,),
                resource_id=last_item.id,
            )
        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    def create_user(
        self,
        command: AdminUserCreate,
        *,
        actor_user_id: UUID,
        request_id: str,
    ) -> AdminUserCreateResult:
        """Provision one active local account and return its temporary password once."""
        temporary_password = secrets.token_urlsafe(16)
        user = self._authentication_service.create_local_account(
            display_name=command.display_name,
            roles=command.roles,
            username=command.username,
            password=temporary_password,
        )
        account = AdminUser(
            id=user.id,
            display_name=user.display_name,
            username=command.username,
            roles=user.roles,
            is_active=user.is_active,
            must_change_password=True,
            created_at=user.created_at,
        )
        logger.info(
            "local account %s created by user %s (request %s; username=%s roles=%s)",
            user.id,
            actor_user_id,
            request_id,
            command.username,
            ",".join(sorted(role.value for role in command.roles)) or "none",
        )
        return AdminUserCreateResult(account=account, temporary_password=temporary_password)


def _normalize_query(query: str | None) -> str | None:
    if query is None:
        return None
    normalized = query.strip().lower()
    return normalized or None


def _resource_for_query(query: str | None) -> str:
    query_sha256 = hashlib.sha256((query or "").encode("utf-8")).hexdigest()
    return f"{_USER_DIRECTORY_RESOURCE}:{query_sha256}"
