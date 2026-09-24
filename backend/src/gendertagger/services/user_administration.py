"""Administrator-facing local-account queries (ADR-0039)."""

import hashlib
import logging
import secrets
from typing import cast
from uuid import UUID

from gendertagger.models.api import CursorPage
from gendertagger.models.auth import (
    AdminUser,
    AdminUserCreate,
    AdminUserCreateResult,
    AdminUserPasswordResetResult,
    AdminUserUpdate,
    normalize_username,
)
from gendertagger.models.user import GlobalRole
from gendertagger.services.authentication import AuthenticationService
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.ports.auth_repository import AdminUserCursor
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

_USER_DIRECTORY_RESOURCE = "admin_users"
logger = logging.getLogger(__name__)


class AdminUserStateConflictError(RuntimeError):
    """Raised when a local-account patch would violate an administrator invariant."""

    def __init__(self, *, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class UserAdministrationService:
    """Administer local accounts without exposing credentials or persistence models."""

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

    def reset_user_password(
        self,
        user_id: UUID,
        *,
        actor_user_id: UUID,
        request_id: str,
    ) -> AdminUserPasswordResetResult:
        """Reset one existing local account without changing its activation state."""
        with self._unit_of_work_factory() as unit_of_work:
            target = unit_of_work.users.get_user_for_update(user_id)
            credential = unit_of_work.auth.get_credential(user_id)
            if target is None or credential is None:
                msg = f"local account {user_id} does not exist"
                raise ResourceNotFoundError(msg)
            temporary_password = secrets.token_urlsafe(16)
            self._authentication_service.reset_password_in_transaction(
                unit_of_work=unit_of_work,
                user_id=user_id,
                new_password=temporary_password,
            )
            unit_of_work.commit()
        logger.info(
            "local account %s password reset by user %s (request %s)",
            user_id,
            actor_user_id,
            request_id,
        )
        return AdminUserPasswordResetResult(temporary_password=temporary_password)

    def update_user(
        self,
        user_id: UUID,
        command: AdminUserUpdate,
        *,
        actor_user_id: UUID,
        request_id: str,
    ) -> AdminUser:
        """Atomically apply a mutable local-account patch with administrator invariants."""
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.users.lock_administrator_updates()
            active_administrator_ids = unit_of_work.users.get_active_administrator_ids()
            if actor_user_id not in active_administrator_ids:
                raise AdminUserStateConflictError(
                    code="acting_user_not_active_administrator",
                    message="The acting account is no longer an active administrator.",
                )
            target = unit_of_work.users.get_user_for_update(user_id)
            credential = unit_of_work.auth.get_credential(user_id)
            if target is None or credential is None:
                msg = f"local account {user_id} does not exist"
                raise ResourceNotFoundError(msg)

            display_name = target.display_name
            roles = target.roles
            is_active = target.is_active
            if "display_name" in command.model_fields_set:
                display_name = cast(str, command.display_name)
            if "roles" in command.model_fields_set:
                roles = cast(set[GlobalRole], command.roles)
            if "is_active" in command.model_fields_set:
                is_active = cast(bool, command.is_active)
            deactivating = target.is_active and not is_active
            if user_id == actor_user_id and not is_active:
                raise AdminUserStateConflictError(
                    code="self_deactivation_forbidden",
                    message="Administrators cannot deactivate their own account.",
                )
            if user_id == actor_user_id and GlobalRole.admin not in roles:
                raise AdminUserStateConflictError(
                    code="self_admin_role_removal_forbidden",
                    message="Administrators cannot remove their own admin role.",
                )
            removes_active_administrator = user_id in active_administrator_ids and (
                not is_active or GlobalRole.admin not in roles
            )
            if removes_active_administrator and len(active_administrator_ids) == 1:
                raise AdminUserStateConflictError(
                    code="last_active_administrator_forbidden",
                    message="At least one active administrator must remain.",
                )

            changed_fields = tuple(
                field
                for field, changed in (
                    ("display_name", display_name != target.display_name),
                    ("roles", roles != target.roles),
                    ("is_active", is_active != target.is_active),
                )
                if changed
            )
            if changed_fields:
                target = unit_of_work.users.update_user(
                    user_id=user_id,
                    display_name=display_name,
                    roles=roles,
                    is_active=is_active,
                )
            if deactivating:
                unit_of_work.auth.revoke_all_sessions(user_id)
            unit_of_work.commit()

        account = AdminUser(
            id=target.id,
            display_name=target.display_name,
            username=credential.username,
            roles=target.roles,
            is_active=target.is_active,
            must_change_password=credential.must_change_password,
            created_at=target.created_at,
        )
        if changed_fields:
            logger.info(
                "local account %s updated by user %s (request %s; fields=%s)",
                user_id,
                actor_user_id,
                request_id,
                ",".join(changed_fields),
            )
        return account


def _normalize_query(query: str | None) -> str | None:
    if query is None:
        return None
    normalized = query.strip().lower()
    return normalized or None


def _resource_for_query(query: str | None) -> str:
    query_sha256 = hashlib.sha256((query or "").encode("utf-8")).hexdigest()
    return f"{_USER_DIRECTORY_RESOURCE}:{query_sha256}"
