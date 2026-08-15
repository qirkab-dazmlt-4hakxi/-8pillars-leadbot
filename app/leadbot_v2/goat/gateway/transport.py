from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Iterable

from .security import (
    new_id,
    sha256_hex,
    utcnow,
)


class NotificationChannel(str, Enum):
    IN_APP = "in_app"
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"


@dataclass
class Notification:
    notification_id: str

    tenant_id: str

    recipient_id: str

    channel: NotificationChannel

    event_type: str

    payload: dict[
        str,
        Any,
    ]

    dedupe_key: str | None

    status: NotificationStatus

    attempts: int = 0

    available_at: datetime = field(
        default_factory=utcnow
    )

    created_at: datetime = field(
        default_factory=utcnow
    )


class NotificationOutbox:
    def __init__(
        self,
        *,
        max_attempts: int = 5,
    ) -> None:
        self.max_attempts = (
            max_attempts
        )

        self.notifications = {}

        self._dedupe = {}

    def enqueue(
        self,
        *,
        tenant_id: str,
        recipient_id: str,
        channel: NotificationChannel,
        event_type: str,
        payload: dict[str, Any],
        dedupe_key: str | None = None,
    ) -> Notification:
        if dedupe_key:
            identity = (
                tenant_id,
                recipient_id,
                channel.value,
                dedupe_key,
            )

            existing = (
                self._dedupe.get(
                    identity
                )
            )

            if existing:
                return (
                    self.notifications[
                        existing
                    ]
                )

        notification = Notification(
            notification_id=new_id(
                "notify"
            ),
            tenant_id=tenant_id,
            recipient_id=(
                recipient_id
            ),
            channel=channel,
            event_type=event_type,
            payload=dict(
                payload
            ),
            dedupe_key=(
                dedupe_key
            ),
            status=(
                NotificationStatus
                .PENDING
            ),
        )

        self.notifications[
            notification
            .notification_id
        ] = notification

        if dedupe_key:
            self._dedupe[
                identity
            ] = (
                notification
                .notification_id
            )

        return notification

    def claim(
        self,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> tuple[
        Notification,
        ...
    ]:
        now = (
            now
            or utcnow()
        )

        eligible = [
            item
            for item
            in self
            .notifications
            .values()
            if (
                item.status
                in {
                    NotificationStatus
                    .PENDING,
                    NotificationStatus
                    .FAILED,
                }
                and item.available_at
                <= now
            )
        ]

        eligible.sort(
            key=lambda item: (
                item.created_at,
                item.notification_id,
            )
        )

        claimed = []

        for item in eligible[
            :limit
        ]:
            item.status = (
                NotificationStatus
                .CLAIMED
            )

            claimed.append(
                item
            )

        return tuple(
            claimed
        )

    def sent(
        self,
        notification_id: str,
    ) -> Notification:
        item = self.notifications[
            notification_id
        ]

        item.status = (
            NotificationStatus.SENT
        )

        return item

    def fail(
        self,
        notification_id: str,
        *,
        now: datetime | None = None,
    ) -> Notification:
        now = (
            now
            or utcnow()
        )

        item = self.notifications[
            notification_id
        ]

        item.attempts += 1

        if (
            item.attempts
            >= self.max_attempts
        ):
            item.status = (
                NotificationStatus.DEAD
            )

        else:
            item.status = (
                NotificationStatus.FAILED
            )

            delay_seconds = min(
                3600,
                (
                    2
                    ** item.attempts
                )
                * 5,
            )

            item.available_at = (
                now
                + timedelta(
                    seconds=(
                        delay_seconds
                    )
                )
            )

        return item


class SyncOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True)
class ServerChange:
    sequence: int

    tenant_id: str

    project_id: str | None

    entity_type: str
    entity_id: str

    operation: SyncOperation

    payload: dict[
        str,
        Any,
    ]

    payload_hash: str

    occurred_at: datetime


@dataclass(frozen=True)
class SyncPage:
    changes: tuple[
        ServerChange,
        ...
    ]

    next_cursor: int

    has_more: bool


class CrossPlatformSyncFeed:
    """
    Append-only server change feed for iPhone, iPad, Android,
    macOS, Windows and web clients.

    Clients retain a sequence cursor. Project filters enforce the
    user's already-authorized project scope.
    """

    def __init__(
        self,
    ) -> None:
        self._changes = []

    def append(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        operation: SyncOperation,
        payload: dict[str, Any],
        project_id: str | None = None,
    ) -> ServerChange:
        change = ServerChange(
            sequence=(
                len(
                    self._changes
                )
                + 1
            ),
            tenant_id=tenant_id,
            project_id=project_id,
            entity_type=(
                entity_type
            ),
            entity_id=(
                entity_id
            ),
            operation=operation,
            payload=dict(
                payload
            ),
            payload_hash=(
                sha256_hex(
                    payload
                )
            ),
            occurred_at=utcnow(),
        )

        self._changes.append(
            change
        )

        return change

    def page(
        self,
        *,
        tenant_id: str,
        cursor: int,
        allowed_project_ids: Iterable[
            str
        ] = (),
        limit: int = 100,
    ) -> SyncPage:
        if cursor < 0:
            raise ValueError(
                "cursor cannot be negative"
            )

        if limit <= 0:
            raise ValueError(
                "limit must be positive"
            )

        projects = frozenset(
            str(item)
            for item
            in allowed_project_ids
        )

        candidates = [
            change
            for change
            in self._changes
            if (
                change.sequence
                > cursor
                and change.tenant_id
                == tenant_id
                and (
                    change.project_id
                    is None
                    or change.project_id
                    in projects
                )
            )
        ]

        selected = candidates[
            :limit
        ]

        next_cursor = (
            selected[
                -1
            ].sequence
            if selected
            else cursor
        )

        return SyncPage(
            changes=tuple(
                selected
            ),
            next_cursor=(
                next_cursor
            ),
            has_more=(
                len(candidates)
                > len(selected)
            ),
        )
