from __future__ import annotations

import hashlib
import secrets

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable

from .security import (
    new_id,
    sha256_hex,
    utcnow,
)


class PortalError(RuntimeError):
    pass


class PortalAccessDenied(PortalError):
    pass


class UploadIntentError(PortalError):
    pass


class PortalPermission(str, Enum):
    VIEW_PROJECT = "view_project"
    VIEW_DOCUMENTS = "view_documents"
    UPLOAD_DOCUMENTS = "upload_documents"
    VIEW_PHOTOS = "view_photos"
    VIEW_SCHEDULE = "view_schedule"
    VIEW_CHANGE_ORDERS = "view_change_orders"
    APPROVE_CHANGE_ORDER = "approve_change_order"
    VIEW_INVOICES = "view_invoices"
    MESSAGE_PROJECT = "message_project"


class ObjectVisibility(str, Enum):
    INTERNAL = "internal"
    PROJECT_TEAM = "project_team"
    CLIENT_PORTAL = "client_portal"
    EXECUTIVE = "executive"


class ObjectStatus(str, Enum):
    PENDING_UPLOAD = "pending_upload"
    VERIFIED = "verified"
    QUARANTINED = "quarantined"
    DELETED = "deleted"


@dataclass(frozen=True)
class PortalGrant:
    grant_id: str

    tenant_id: str
    principal_id: str

    project_ids: frozenset[
        str
    ]

    permissions: frozenset[
        PortalPermission
    ]

    expires_at: datetime | None = None


class PortalAuthorizationService:
    def __init__(
        self,
    ) -> None:
        self._grants = {}

    def grant(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        project_ids: Iterable[str],
        permissions: Iterable[
            PortalPermission
        ],
        expires_at: datetime | None = None,
    ) -> PortalGrant:
        project_set = frozenset(
            str(item)
            for item
            in project_ids
            if str(item).strip()
        )

        if not project_set:
            raise ValueError(
                "portal grant requires project"
            )

        permission_set = frozenset(
            permissions
        )

        if not permission_set:
            raise ValueError(
                "portal grant requires permission"
            )

        grant = PortalGrant(
            grant_id=new_id(
                "portalgrant"
            ),
            tenant_id=str(
                tenant_id
            ),
            principal_id=str(
                principal_id
            ),
            project_ids=project_set,
            permissions=permission_set,
            expires_at=expires_at,
        )

        self._grants[
            grant.grant_id
        ] = grant

        return grant

    def require(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        project_id: str,
        permission: PortalPermission,
        now: datetime | None = None,
    ) -> PortalGrant:
        now = (
            now
            or utcnow()
        )

        candidates = [
            grant
            for grant
            in self._grants.values()
            if (
                grant.tenant_id
                == tenant_id
                and grant.principal_id
                == principal_id
                and project_id
                in grant.project_ids
                and permission
                in grant.permissions
                and (
                    grant.expires_at
                    is None
                    or now
                    < grant.expires_at
                )
            )
        ]

        if not candidates:
            raise PortalAccessDenied(
                (
                    f"{principal_id}:"
                    f"{project_id}:"
                    f"{permission.value}"
                )
            )

        return candidates[0]


@dataclass
class ObjectRecord:
    object_id: str

    tenant_id: str
    project_id: str | None

    filename: str
    mime_type: str

    size_bytes: int

    expected_sha256: str

    visibility: ObjectVisibility

    created_by: str

    status: ObjectStatus

    verified_sha256: str | None = None

    created_at: datetime = field(
        default_factory=utcnow
    )


@dataclass(frozen=True)
class UploadIntent:
    intent_id: str
    object_id: str

    upload_token: str

    expires_at: datetime


@dataclass
class _IntentState:
    token_hash: str

    object_id: str

    expires_at: datetime

    used: bool = False


class SecureObjectRegistry:
    def __init__(
        self,
        *,
        max_upload_bytes: int = (
            250
            * 1024
            * 1024
        ),
    ) -> None:
        self.max_upload_bytes = (
            max_upload_bytes
        )

        self.objects = {}

        self._intents = {}

    def create_upload_intent(
        self,
        *,
        tenant_id: str,
        project_id: str | None,
        filename: str,
        mime_type: str,
        size_bytes: int,
        expected_sha256: str,
        visibility: ObjectVisibility,
        created_by: str,
        lifetime: timedelta = timedelta(
            minutes=15
        ),
        now: datetime | None = None,
    ) -> UploadIntent:
        now = (
            now
            or utcnow()
        )

        if (
            size_bytes <= 0
            or size_bytes
            > self.max_upload_bytes
        ):
            raise UploadIntentError(
                "invalid upload size"
            )

        expected_sha256 = (
            expected_sha256
            .strip()
            .lower()
        )

        if (
            len(expected_sha256)
            != 64
            or any(
                ch
                not in "0123456789abcdef"
                for ch
                in expected_sha256
            )
        ):
            raise UploadIntentError(
                "invalid sha256"
            )

        object_record = ObjectRecord(
            object_id=new_id(
                "object"
            ),
            tenant_id=str(
                tenant_id
            ),
            project_id=(
                str(project_id)
                if project_id
                else None
            ),
            filename=str(
                filename
            ),
            mime_type=str(
                mime_type
            ).lower(),
            size_bytes=int(
                size_bytes
            ),
            expected_sha256=(
                expected_sha256
            ),
            visibility=visibility,
            created_by=str(
                created_by
            ),
            status=(
                ObjectStatus
                .PENDING_UPLOAD
            ),
        )

        self.objects[
            object_record.object_id
        ] = object_record

        raw_token = (
            secrets
            .token_urlsafe(
                32
            )
        )

        intent_id = new_id(
            "upload"
        )

        expires = (
            now
            + lifetime
        )

        self._intents[
            intent_id
        ] = _IntentState(
            token_hash=hashlib.sha256(
                raw_token.encode(
                    "utf-8"
                )
            ).hexdigest(),
            object_id=(
                object_record
                .object_id
            ),
            expires_at=expires,
        )

        return UploadIntent(
            intent_id=intent_id,
            object_id=(
                object_record
                .object_id
            ),
            upload_token=raw_token,
            expires_at=expires,
        )

    def verify_upload(
        self,
        *,
        intent_id: str,
        upload_token: str,
        content: bytes,
        now: datetime | None = None,
    ) -> ObjectRecord:
        now = (
            now
            or utcnow()
        )

        try:
            state = self._intents[
                intent_id
            ]

        except KeyError as exc:
            raise UploadIntentError(
                "unknown upload intent"
            ) from exc

        if state.used:
            raise UploadIntentError(
                "upload intent already used"
            )

        if now >= state.expires_at:
            raise UploadIntentError(
                "upload intent expired"
            )

        received_token_hash = (
            hashlib.sha256(
                upload_token.encode(
                    "utf-8"
                )
            ).hexdigest()
        )

        if not secrets.compare_digest(
            state.token_hash,
            received_token_hash,
        ):
            raise UploadIntentError(
                "invalid upload token"
            )

        record = self.objects[
            state.object_id
        ]

        actual_size = len(
            content
        )

        actual_hash = (
            hashlib.sha256(
                content
            ).hexdigest()
        )

        state.used = True

        if (
            actual_size
            != record.size_bytes
            or actual_hash
            != record.expected_sha256
        ):
            record.status = (
                ObjectStatus.QUARANTINED
            )

            record.verified_sha256 = (
                actual_hash
            )

            raise UploadIntentError(
                "uploaded object integrity mismatch"
            )

        record.status = (
            ObjectStatus.VERIFIED
        )

        record.verified_sha256 = (
            actual_hash
        )

        return record
