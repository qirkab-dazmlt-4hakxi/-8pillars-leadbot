from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import threading
import uuid

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from pathlib import Path
from typing import Any, Iterator, Sequence

from .models import (
    BackupResult,
    DataIntegrityError,
    DuplicateMessageConflict,
    DurableEvent,
    EntityRecord,
    IdempotencyConflict,
    Lease,
    LeaseBusy,
    LeaseLost,
    OptimisticConcurrencyError,
    OutboxMessage,
    OutboxStatus,
    PersistenceHealth,
    PersistenceValidationError,
    Snapshot,
)


def utcnow() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _id(prefix: str) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def _dt(
    value: datetime,
) -> str:
    if value.tzinfo is None:
        raise PersistenceValidationError(
            "datetime must be timezone aware"
        )

    return (
        value.astimezone(
            timezone.utc
        )
        .isoformat()
    )


def _parse_dt(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    return datetime.fromisoformat(
        value
    )


def canonical_json(
    value: Any,
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def payload_hash(
    value: Any,
) -> str:
    return hashlib.sha256(
        canonical_json(
            value
        ).encode("utf-8")
    ).hexdigest()


def _required(
    value: str,
    name: str,
) -> str:
    result = str(
        value
        or ""
    ).strip()

    if not result:
        raise PersistenceValidationError(
            f"{name} is required"
        )

    return result


class EnterprisePersistenceStore:
    """
    Transactional durable reference backend for GOAT OS.

    SQLite WAL is used for deterministic local/dev/test durability.
    The public persistence contract intentionally avoids SQLite-specific
    domain semantics so a PostgreSQL implementation can replace this
    backend without changing GOAT business logic.
    """

    SCHEMA_VERSION = 2

    def __init__(
        self,
        path: str | Path,
        *,
        busy_timeout_ms: int = 5000,
    ) -> None:
        self.path = Path(
            path
        )

        if (
            str(self.path)
            != ":memory:"
        ):
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

        self._lock = (
            threading.RLock()
        )

        self._connection = (
            sqlite3.connect(
                str(
                    self.path
                ),
                isolation_level=None,
                check_same_thread=False,
            )
        )

        self._connection.row_factory = (
            sqlite3.Row
        )

        self._connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        self._connection.execute(
            (
                "PRAGMA busy_timeout = "
                + str(
                    int(
                        busy_timeout_ms
                    )
                )
            )
        )

        self._connection.execute(
            "PRAGMA synchronous = FULL"
        )

        if (
            str(self.path)
            != ":memory:"
        ):
            self._connection.execute(
                "PRAGMA journal_mode = WAL"
            )

        self.migrate()

    def close(
        self,
    ) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(
        self,
    ) -> "EnterprisePersistenceStore":
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        self.close()

    @contextlib.contextmanager
    def transaction(
        self,
    ) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute(
                "BEGIN IMMEDIATE"
            )

            try:
                yield self._connection

            except Exception:
                self._connection.execute(
                    "ROLLBACK"
                )

                raise

            else:
                self._connection.execute(
                    "COMMIT"
                )

    # ========================================================
    # MIGRATIONS
    # ========================================================

    def migrate(
        self,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )

        migrations = {
            1: [
                """
                CREATE TABLE IF NOT EXISTS entities (
                    tenant_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,

                    version INTEGER NOT NULL,

                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,

                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,

                    PRIMARY KEY (
                        tenant_id,
                        entity_type,
                        entity_id
                    )
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS durable_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,

                    event_id TEXT NOT NULL UNIQUE,

                    tenant_id TEXT NOT NULL,

                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,

                    aggregate_version INTEGER NOT NULL,

                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL,

                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,

                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,

                    occurred_at TEXT NOT NULL
                )
                """,
                """
                CREATE INDEX IF NOT EXISTS
                idx_durable_events_tenant_sequence
                ON durable_events (
                    tenant_id,
                    sequence
                )
                """,
            ],

            2: [
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    outbox_id TEXT PRIMARY KEY,

                    tenant_id TEXT NOT NULL,

                    topic TEXT NOT NULL,

                    aggregate_type TEXT,
                    aggregate_id TEXT,

                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,

                    status TEXT NOT NULL,

                    attempts INTEGER NOT NULL DEFAULT 0,

                    available_at TEXT NOT NULL,

                    locked_by TEXT,
                    lease_expires_at TEXT,

                    dedupe_key TEXT,

                    created_at TEXT NOT NULL,

                    UNIQUE (
                        tenant_id,
                        topic,
                        dedupe_key
                    )
                )
                """,
                """
                CREATE INDEX IF NOT EXISTS
                idx_outbox_delivery
                ON outbox (
                    status,
                    available_at
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS inbox (
                    tenant_id TEXT NOT NULL,

                    consumer TEXT NOT NULL,
                    message_id TEXT NOT NULL,

                    payload_hash TEXT NOT NULL,

                    processed_at TEXT NOT NULL,

                    PRIMARY KEY (
                        tenant_id,
                        consumer,
                        message_id
                    )
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS idempotency (
                    tenant_id TEXT NOT NULL,

                    scope TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,

                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,

                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,

                    PRIMARY KEY (
                        tenant_id,
                        scope,
                        idempotency_key
                    )
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS leases (
                    lease_name TEXT PRIMARY KEY,

                    owner_id TEXT NOT NULL,

                    fencing_token INTEGER NOT NULL,

                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,

                    tenant_id TEXT NOT NULL,

                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,

                    entity_version INTEGER NOT NULL,

                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,

                    created_at TEXT NOT NULL
                )
                """,
                """
                CREATE INDEX IF NOT EXISTS
                idx_snapshot_entity
                ON snapshots (
                    tenant_id,
                    entity_type,
                    entity_id,
                    entity_version
                )
                """,
            ],
        }

        current = self.schema_version()

        for version in range(
            current + 1,
            self.SCHEMA_VERSION + 1,
        ):
            statements = (
                migrations[
                    version
                ]
            )

            with self.transaction() as db:
                for statement in statements:
                    db.execute(
                        statement
                    )

                db.execute(
                    """
                    INSERT INTO schema_migrations (
                        version,
                        applied_at
                    )
                    VALUES (?, ?)
                    """,
                    (
                        version,
                        _dt(
                            utcnow()
                        ),
                    ),
                )

    def schema_version(
        self,
    ) -> int:
        row = self._connection.execute(
            """
            SELECT COALESCE(
                MAX(version),
                0
            ) AS version
            FROM schema_migrations
            """
        ).fetchone()

        return int(
            row["version"]
        )

    # ========================================================
    # ENTITY STORAGE
    # ========================================================

    @staticmethod
    def _entity_from_row(
        row: sqlite3.Row,
    ) -> EntityRecord:
        payload = json.loads(
            row["payload_json"]
        )

        calculated = payload_hash(
            payload
        )

        if (
            calculated
            != row["payload_hash"]
        ):
            raise DataIntegrityError(
                "entity payload hash mismatch"
            )

        return EntityRecord(
            tenant_id=(
                row["tenant_id"]
            ),
            entity_type=(
                row["entity_type"]
            ),
            entity_id=(
                row["entity_id"]
            ),
            version=int(
                row["version"]
            ),
            payload=payload,
            payload_hash=(
                row["payload_hash"]
            ),
            created_at=_parse_dt(
                row["created_at"]
            ),
            updated_at=_parse_dt(
                row["updated_at"]
            ),
            deleted_at=_parse_dt(
                row["deleted_at"]
            ),
        )

    def get_entity(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        include_deleted: bool = False,
    ) -> EntityRecord | None:
        tenant_id = _required(
            tenant_id,
            "tenant_id",
        )

        row = self._connection.execute(
            """
            SELECT *
            FROM entities
            WHERE tenant_id = ?
              AND entity_type = ?
              AND entity_id = ?
            """,
            (
                tenant_id,
                _required(
                    entity_type,
                    "entity_type",
                ),
                _required(
                    entity_id,
                    "entity_id",
                ),
            ),
        ).fetchone()

        if row is None:
            return None

        record = self._entity_from_row(
            row
        )

        if (
            record.deleted_at
            is not None
            and not include_deleted
        ):
            return None

        return record

    def list_entities(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        include_deleted: bool = False,
    ) -> tuple[
        EntityRecord,
        ...
    ]:
        tenant_id = _required(
            tenant_id,
            "tenant_id",
        )

        sql = """
            SELECT *
            FROM entities
            WHERE tenant_id = ?
              AND entity_type = ?
        """

        params = [
            tenant_id,
            _required(
                entity_type,
                "entity_type",
            ),
        ]

        if not include_deleted:
            sql += (
                " AND deleted_at IS NULL"
            )

        sql += (
            " ORDER BY entity_id"
        )

        rows = self._connection.execute(
            sql,
            params,
        ).fetchall()

        return tuple(
            self._entity_from_row(
                row
            )
            for row
            in rows
        )

    def put_entity(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        actor_id: str,
        expected_version: int | None = None,
    ) -> EntityRecord:
        tenant_id = _required(
            tenant_id,
            "tenant_id",
        )

        entity_type = _required(
            entity_type,
            "entity_type",
        )

        entity_id = _required(
            entity_id,
            "entity_id",
        )

        actor_id = _required(
            actor_id,
            "actor_id",
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise PersistenceValidationError(
                "entity payload must be object"
            )

        now = utcnow()

        serialized = canonical_json(
            payload
        )

        digest = payload_hash(
            payload
        )

        with self.transaction() as db:
            existing = db.execute(
                """
                SELECT *
                FROM entities
                WHERE tenant_id = ?
                  AND entity_type = ?
                  AND entity_id = ?
                """,
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                ),
            ).fetchone()

            if existing is None:
                if (
                    expected_version
                    not in {
                        None,
                        0,
                    }
                ):
                    raise OptimisticConcurrencyError(
                        "entity does not yet exist"
                    )

                version = 1

                db.execute(
                    """
                    INSERT INTO entities (
                        tenant_id,
                        entity_type,
                        entity_id,
                        version,
                        payload_json,
                        payload_hash,
                        created_at,
                        updated_at,
                        deleted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        tenant_id,
                        entity_type,
                        entity_id,
                        version,
                        serialized,
                        digest,
                        _dt(now),
                        _dt(now),
                    ),
                )

                event_type = (
                    "entity.created"
                )

            else:
                current_version = int(
                    existing["version"]
                )

                if expected_version is None:
                    raise OptimisticConcurrencyError(
                        "expected_version required for update"
                    )

                if (
                    expected_version
                    != current_version
                ):
                    raise OptimisticConcurrencyError(
                        (
                            "version mismatch: "
                            f"expected={expected_version} "
                            f"actual={current_version}"
                        )
                    )

                version = (
                    current_version
                    + 1
                )

                db.execute(
                    """
                    UPDATE entities
                    SET version = ?,
                        payload_json = ?,
                        payload_hash = ?,
                        updated_at = ?,
                        deleted_at = NULL
                    WHERE tenant_id = ?
                      AND entity_type = ?
                      AND entity_id = ?
                      AND version = ?
                    """,
                    (
                        version,
                        serialized,
                        digest,
                        _dt(now),
                        tenant_id,
                        entity_type,
                        entity_id,
                        current_version,
                    ),
                )

                if db.total_changes <= 0:
                    raise OptimisticConcurrencyError(
                        "concurrent update detected"
                    )

                event_type = (
                    "entity.updated"
                )

            self._append_event_locked(
                db=db,
                tenant_id=tenant_id,
                aggregate_type=(
                    entity_type
                ),
                aggregate_id=(
                    entity_id
                ),
                aggregate_version=(
                    version
                ),
                event_type=(
                    event_type
                ),
                actor_id=actor_id,
                payload={
                    "entity_hash":
                        digest,
                    "version":
                        version,
                },
            )

        result = self.get_entity(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            include_deleted=True,
        )

        assert result is not None

        return result

    def delete_entity(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        expected_version: int,
        actor_id: str,
    ) -> EntityRecord:
        now = utcnow()

        with self.transaction() as db:
            row = db.execute(
                """
                SELECT *
                FROM entities
                WHERE tenant_id = ?
                  AND entity_type = ?
                  AND entity_id = ?
                """,
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                ),
            ).fetchone()

            if row is None:
                raise OptimisticConcurrencyError(
                    "entity does not exist"
                )

            current = int(
                row["version"]
            )

            if current != expected_version:
                raise OptimisticConcurrencyError(
                    "delete version mismatch"
                )

            next_version = (
                current
                + 1
            )

            db.execute(
                """
                UPDATE entities
                SET version = ?,
                    updated_at = ?,
                    deleted_at = ?
                WHERE tenant_id = ?
                  AND entity_type = ?
                  AND entity_id = ?
                  AND version = ?
                """,
                (
                    next_version,
                    _dt(now),
                    _dt(now),
                    tenant_id,
                    entity_type,
                    entity_id,
                    current,
                ),
            )

            self._append_event_locked(
                db=db,
                tenant_id=tenant_id,
                aggregate_type=(
                    entity_type
                ),
                aggregate_id=(
                    entity_id
                ),
                aggregate_version=(
                    next_version
                ),
                event_type=(
                    "entity.deleted"
                ),
                actor_id=actor_id,
                payload={
                    "version":
                        next_version
                },
            )

        result = self.get_entity(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            include_deleted=True,
        )

        assert result is not None

        return result

    # ========================================================
    # IMMUTABLE EVENT CHAIN
    # ========================================================

    def _append_event_locked(
        self,
        *,
        db: sqlite3.Connection,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
    ) -> DurableEvent:
        previous = db.execute(
            """
            SELECT event_hash
            FROM durable_events
            WHERE tenant_id = ?
            ORDER BY sequence DESC
            LIMIT 1
            """,
            (
                tenant_id,
            ),
        ).fetchone()

        previous_hash = (
            previous["event_hash"]
            if previous
            else "0" * 64
        )

        event_id = _id(
            "event"
        )

        occurred_at = utcnow()

        digest = payload_hash(
            payload
        )

        event_hash = payload_hash(
            {
                "event_id":
                    event_id,
                "tenant_id":
                    tenant_id,
                "aggregate_type":
                    aggregate_type,
                "aggregate_id":
                    aggregate_id,
                "aggregate_version":
                    aggregate_version,
                "event_type":
                    event_type,
                "actor_id":
                    actor_id,
                "payload_hash":
                    digest,
                "previous_hash":
                    previous_hash,
                "occurred_at":
                    _dt(
                        occurred_at
                    ),
            }
        )

        cursor = db.execute(
            """
            INSERT INTO durable_events (
                event_id,
                tenant_id,
                aggregate_type,
                aggregate_id,
                aggregate_version,
                event_type,
                actor_id,
                payload_json,
                payload_hash,
                previous_hash,
                event_hash,
                occurred_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                tenant_id,
                aggregate_type,
                aggregate_id,
                aggregate_version,
                event_type,
                actor_id,
                canonical_json(
                    payload
                ),
                digest,
                previous_hash,
                event_hash,
                _dt(
                    occurred_at
                ),
            ),
        )

        return DurableEvent(
            sequence=int(
                cursor.lastrowid
            ),
            event_id=event_id,
            tenant_id=tenant_id,
            aggregate_type=(
                aggregate_type
            ),
            aggregate_id=(
                aggregate_id
            ),
            aggregate_version=(
                aggregate_version
            ),
            event_type=event_type,
            actor_id=actor_id,
            payload=dict(
                payload
            ),
            payload_hash=digest,
            previous_hash=(
                previous_hash
            ),
            event_hash=(
                event_hash
            ),
            occurred_at=(
                occurred_at
            ),
        )

    def append_event(
        self,
        *,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
    ) -> DurableEvent:
        with self.transaction() as db:
            return self._append_event_locked(
                db=db,
                tenant_id=_required(
                    tenant_id,
                    "tenant_id",
                ),
                aggregate_type=_required(
                    aggregate_type,
                    "aggregate_type",
                ),
                aggregate_id=_required(
                    aggregate_id,
                    "aggregate_id",
                ),
                aggregate_version=int(
                    aggregate_version
                ),
                event_type=_required(
                    event_type,
                    "event_type",
                ),
                actor_id=_required(
                    actor_id,
                    "actor_id",
                ),
                payload=dict(
                    payload
                ),
            )

    def verify_event_chain(
        self,
        *,
        tenant_id: str,
    ) -> bool:
        rows = self._connection.execute(
            """
            SELECT *
            FROM durable_events
            WHERE tenant_id = ?
            ORDER BY sequence
            """,
            (
                tenant_id,
            ),
        ).fetchall()

        previous_hash = (
            "0" * 64
        )

        for row in rows:
            payload = json.loads(
                row["payload_json"]
            )

            digest = payload_hash(
                payload
            )

            if (
                digest
                != row["payload_hash"]
            ):
                raise DataIntegrityError(
                    "event payload tampered"
                )

            if (
                row["previous_hash"]
                != previous_hash
            ):
                raise DataIntegrityError(
                    "event chain broken"
                )

            calculated = payload_hash(
                {
                    "event_id":
                        row["event_id"],
                    "tenant_id":
                        row["tenant_id"],
                    "aggregate_type":
                        row["aggregate_type"],
                    "aggregate_id":
                        row["aggregate_id"],
                    "aggregate_version":
                        int(
                            row[
                                "aggregate_version"
                            ]
                        ),
                    "event_type":
                        row["event_type"],
                    "actor_id":
                        row["actor_id"],
                    "payload_hash":
                        row["payload_hash"],
                    "previous_hash":
                        row["previous_hash"],
                    "occurred_at":
                        row["occurred_at"],
                }
            )

            if (
                calculated
                != row["event_hash"]
            ):
                raise DataIntegrityError(
                    "event hash mismatch"
                )

            previous_hash = (
                row["event_hash"]
            )

        return True

    # ========================================================
    # OUTBOX
    # ========================================================

    def enqueue_outbox(
        self,
        *,
        tenant_id: str,
        topic: str,
        payload: dict[str, Any],
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        dedupe_key: str | None = None,
        available_at: datetime | None = None,
    ) -> str:
        tenant_id = _required(
            tenant_id,
            "tenant_id",
        )

        topic = _required(
            topic,
            "topic",
        )

        now = utcnow()

        available = (
            available_at
            or now
        )

        digest = payload_hash(
            payload
        )

        if dedupe_key:
            existing = self._connection.execute(
                """
                SELECT outbox_id
                FROM outbox
                WHERE tenant_id = ?
                  AND topic = ?
                  AND dedupe_key = ?
                """,
                (
                    tenant_id,
                    topic,
                    dedupe_key,
                ),
            ).fetchone()

            if existing:
                return str(
                    existing[
                        "outbox_id"
                    ]
                )

        outbox_id = _id(
            "outbox"
        )

        with self.transaction() as db:
            db.execute(
                """
                INSERT INTO outbox (
                    outbox_id,
                    tenant_id,
                    topic,
                    aggregate_type,
                    aggregate_id,
                    payload_json,
                    payload_hash,
                    status,
                    attempts,
                    available_at,
                    locked_by,
                    lease_expires_at,
                    dedupe_key,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, NULL, ?, ?)
                """,
                (
                    outbox_id,
                    tenant_id,
                    topic,
                    aggregate_type,
                    aggregate_id,
                    canonical_json(
                        payload
                    ),
                    digest,
                    OutboxStatus
                    .PENDING
                    .value,
                    _dt(
                        available
                    ),
                    dedupe_key,
                    _dt(now),
                ),
            )

        return outbox_id

    @staticmethod
    def _outbox_from_row(
        row: sqlite3.Row,
    ) -> OutboxMessage:
        payload = json.loads(
            row["payload_json"]
        )

        if (
            payload_hash(
                payload
            )
            != row["payload_hash"]
        ):
            raise DataIntegrityError(
                "outbox payload hash mismatch"
            )

        return OutboxMessage(
            outbox_id=(
                row["outbox_id"]
            ),
            tenant_id=(
                row["tenant_id"]
            ),
            topic=(
                row["topic"]
            ),
            aggregate_type=(
                row["aggregate_type"]
            ),
            aggregate_id=(
                row["aggregate_id"]
            ),
            payload=payload,
            payload_hash=(
                row["payload_hash"]
            ),
            status=OutboxStatus(
                row["status"]
            ),
            attempts=int(
                row["attempts"]
            ),
            available_at=_parse_dt(
                row["available_at"]
            ),
            locked_by=(
                row["locked_by"]
            ),
            lease_expires_at=_parse_dt(
                row[
                    "lease_expires_at"
                ]
            ),
            dedupe_key=(
                row["dedupe_key"]
            ),
            created_at=_parse_dt(
                row["created_at"]
            ),
        )

    def claim_outbox(
        self,
        *,
        worker_id: str,
        limit: int = 20,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> tuple[
        OutboxMessage,
        ...
    ]:
        worker_id = _required(
            worker_id,
            "worker_id",
        )

        if limit <= 0:
            raise PersistenceValidationError(
                "limit must be positive"
            )

        now = (
            now
            or utcnow()
        )

        lease_expires = (
            now
            + timedelta(
                seconds=max(
                    1,
                    int(
                        lease_seconds
                    ),
                )
            )
        )

        ids = []

        with self.transaction() as db:
            rows = db.execute(
                """
                SELECT outbox_id
                FROM outbox
                WHERE (
                    status = ?
                    OR status = ?
                    OR (
                        status = ?
                        AND lease_expires_at < ?
                    )
                )
                  AND available_at <= ?
                ORDER BY created_at, outbox_id
                LIMIT ?
                """,
                (
                    OutboxStatus
                    .PENDING
                    .value,
                    OutboxStatus
                    .FAILED
                    .value,
                    OutboxStatus
                    .CLAIMED
                    .value,
                    _dt(now),
                    _dt(now),
                    int(limit),
                ),
            ).fetchall()

            ids = [
                str(
                    row["outbox_id"]
                )
                for row
                in rows
            ]

            for outbox_id in ids:
                db.execute(
                    """
                    UPDATE outbox
                    SET status = ?,
                        locked_by = ?,
                        lease_expires_at = ?
                    WHERE outbox_id = ?
                    """,
                    (
                        OutboxStatus
                        .CLAIMED
                        .value,
                        worker_id,
                        _dt(
                            lease_expires
                        ),
                        outbox_id,
                    ),
                )

        result = []

        for outbox_id in ids:
            row = self._connection.execute(
                """
                SELECT *
                FROM outbox
                WHERE outbox_id = ?
                """,
                (
                    outbox_id,
                ),
            ).fetchone()

            result.append(
                self._outbox_from_row(
                    row
                )
            )

        return tuple(
            result
        )

    def complete_outbox(
        self,
        *,
        outbox_id: str,
        worker_id: str,
    ) -> None:
        with self.transaction() as db:
            row = db.execute(
                """
                SELECT *
                FROM outbox
                WHERE outbox_id = ?
                """,
                (
                    outbox_id,
                ),
            ).fetchone()

            if row is None:
                raise PersistenceValidationError(
                    "outbox message not found"
                )

            if (
                row["status"]
                != OutboxStatus
                .CLAIMED
                .value
                or row["locked_by"]
                != worker_id
            ):
                raise LeaseLost(
                    "outbox delivery lease lost"
                )

            db.execute(
                """
                UPDATE outbox
                SET status = ?,
                    locked_by = NULL,
                    lease_expires_at = NULL
                WHERE outbox_id = ?
                """,
                (
                    OutboxStatus
                    .DELIVERED
                    .value,
                    outbox_id,
                ),
            )

    def fail_outbox(
        self,
        *,
        outbox_id: str,
        worker_id: str,
        max_attempts: int = 5,
        now: datetime | None = None,
    ) -> None:
        now = (
            now
            or utcnow()
        )

        with self.transaction() as db:
            row = db.execute(
                """
                SELECT *
                FROM outbox
                WHERE outbox_id = ?
                """,
                (
                    outbox_id,
                ),
            ).fetchone()

            if (
                row is None
                or row["locked_by"]
                != worker_id
            ):
                raise LeaseLost(
                    "outbox delivery lease lost"
                )

            attempts = (
                int(
                    row["attempts"]
                )
                + 1
            )

            if attempts >= max_attempts:
                status = (
                    OutboxStatus
                    .DEAD
                )

                available = now

            else:
                status = (
                    OutboxStatus
                    .FAILED
                )

                delay = min(
                    3600,
                    (
                        2
                        ** attempts
                    )
                    * 5,
                )

                available = (
                    now
                    + timedelta(
                        seconds=delay
                    )
                )

            db.execute(
                """
                UPDATE outbox
                SET status = ?,
                    attempts = ?,
                    available_at = ?,
                    locked_by = NULL,
                    lease_expires_at = NULL
                WHERE outbox_id = ?
                """,
                (
                    status.value,
                    attempts,
                    _dt(
                        available
                    ),
                    outbox_id,
                ),
            )

    # ========================================================
    # INBOX
    # ========================================================

    def record_inbox(
        self,
        *,
        tenant_id: str,
        consumer: str,
        message_id: str,
        payload: dict[str, Any],
    ) -> bool:
        digest = payload_hash(
            payload
        )

        existing = self._connection.execute(
            """
            SELECT payload_hash
            FROM inbox
            WHERE tenant_id = ?
              AND consumer = ?
              AND message_id = ?
            """,
            (
                tenant_id,
                consumer,
                message_id,
            ),
        ).fetchone()

        if existing:
            if (
                existing["payload_hash"]
                != digest
            ):
                raise DuplicateMessageConflict(
                    "message ID reused with different payload"
                )

            return False

        with self.transaction() as db:
            db.execute(
                """
                INSERT INTO inbox (
                    tenant_id,
                    consumer,
                    message_id,
                    payload_hash,
                    processed_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    consumer,
                    message_id,
                    digest,
                    _dt(
                        utcnow()
                    ),
                ),
            )

        return True

    # ========================================================
    # IDEMPOTENCY
    # ========================================================

    def save_idempotency(
        self,
        *,
        tenant_id: str,
        scope: str,
        key: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        ttl: timedelta = timedelta(
            hours=24
        ),
    ) -> None:
        now = utcnow()

        request_digest = payload_hash(
            request_payload
        )

        existing = self._connection.execute(
            """
            SELECT request_hash
            FROM idempotency
            WHERE tenant_id = ?
              AND scope = ?
              AND idempotency_key = ?
            """,
            (
                tenant_id,
                scope,
                key,
            ),
        ).fetchone()

        if existing:
            if (
                existing["request_hash"]
                != request_digest
            ):
                raise IdempotencyConflict(
                    key
                )

            return

        with self.transaction() as db:
            db.execute(
                """
                INSERT INTO idempotency (
                    tenant_id,
                    scope,
                    idempotency_key,
                    request_hash,
                    response_json,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    scope,
                    key,
                    request_digest,
                    canonical_json(
                        response_payload
                    ),
                    _dt(now),
                    _dt(
                        now
                        + ttl
                    ),
                ),
            )

    def get_idempotency(
        self,
        *,
        tenant_id: str,
        scope: str,
        key: str,
        request_payload: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        now = (
            now
            or utcnow()
        )

        row = self._connection.execute(
            """
            SELECT *
            FROM idempotency
            WHERE tenant_id = ?
              AND scope = ?
              AND idempotency_key = ?
            """,
            (
                tenant_id,
                scope,
                key,
            ),
        ).fetchone()

        if row is None:
            return None

        if (
            _parse_dt(
                row["expires_at"]
            )
            <= now
        ):
            return None

        digest = payload_hash(
            request_payload
        )

        if (
            row["request_hash"]
            != digest
        ):
            raise IdempotencyConflict(
                key
            )

        return json.loads(
            row["response_json"]
        )

    # ========================================================
    # DISTRIBUTED LEASE / FENCING
    # ========================================================

    def acquire_lease(
        self,
        *,
        lease_name: str,
        owner_id: str,
        ttl: timedelta,
        now: datetime | None = None,
    ) -> Lease:
        lease_name = _required(
            lease_name,
            "lease_name",
        )

        owner_id = _required(
            owner_id,
            "owner_id",
        )

        now = (
            now
            or utcnow()
        )

        if ttl.total_seconds() <= 0:
            raise PersistenceValidationError(
                "lease TTL must be positive"
            )

        expires = (
            now
            + ttl
        )

        with self.transaction() as db:
            row = db.execute(
                """
                SELECT *
                FROM leases
                WHERE lease_name = ?
                """,
                (
                    lease_name,
                ),
            ).fetchone()

            if row is None:
                token = 1

                db.execute(
                    """
                    INSERT INTO leases (
                        lease_name,
                        owner_id,
                        fencing_token,
                        expires_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        lease_name,
                        owner_id,
                        token,
                        _dt(
                            expires
                        ),
                        _dt(now),
                    ),
                )

            else:
                current_expiry = (
                    _parse_dt(
                        row[
                            "expires_at"
                        ]
                    )
                )

                current_owner = (
                    row["owner_id"]
                )

                token = int(
                    row[
                        "fencing_token"
                    ]
                )

                if (
                    current_expiry
                    > now
                    and current_owner
                    != owner_id
                ):
                    raise LeaseBusy(
                        lease_name
                    )

                if (
                    current_owner
                    != owner_id
                    or current_expiry
                    <= now
                ):
                    token += 1

                db.execute(
                    """
                    UPDATE leases
                    SET owner_id = ?,
                        fencing_token = ?,
                        expires_at = ?,
                        updated_at = ?
                    WHERE lease_name = ?
                    """,
                    (
                        owner_id,
                        token,
                        _dt(
                            expires
                        ),
                        _dt(now),
                        lease_name,
                    ),
                )

        return Lease(
            lease_name=lease_name,
            owner_id=owner_id,
            fencing_token=token,
            expires_at=expires,
        )

    def renew_lease(
        self,
        *,
        lease_name: str,
        owner_id: str,
        fencing_token: int,
        ttl: timedelta,
        now: datetime | None = None,
    ) -> Lease:
        now = (
            now
            or utcnow()
        )

        expires = (
            now
            + ttl
        )

        with self.transaction() as db:
            row = db.execute(
                """
                SELECT *
                FROM leases
                WHERE lease_name = ?
                """,
                (
                    lease_name,
                ),
            ).fetchone()

            if row is None:
                raise LeaseLost(
                    lease_name
                )

            if (
                row["owner_id"]
                != owner_id
                or int(
                    row[
                        "fencing_token"
                    ]
                )
                != fencing_token
                or _parse_dt(
                    row[
                        "expires_at"
                    ]
                )
                <= now
            ):
                raise LeaseLost(
                    lease_name
                )

            db.execute(
                """
                UPDATE leases
                SET expires_at = ?,
                    updated_at = ?
                WHERE lease_name = ?
                """,
                (
                    _dt(
                        expires
                    ),
                    _dt(now),
                    lease_name,
                ),
            )

        return Lease(
            lease_name=lease_name,
            owner_id=owner_id,
            fencing_token=(
                fencing_token
            ),
            expires_at=expires,
        )

    # ========================================================
    # SNAPSHOTS
    # ========================================================

    def create_snapshot(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
    ) -> Snapshot:
        record = self.get_entity(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            include_deleted=True,
        )

        if record is None:
            raise PersistenceValidationError(
                "entity not found"
            )

        snapshot = Snapshot(
            snapshot_id=_id(
                "snapshot"
            ),
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_version=(
                record.version
            ),
            payload=dict(
                record.payload
            ),
            payload_hash=(
                record.payload_hash
            ),
            created_at=utcnow(),
        )

        with self.transaction() as db:
            db.execute(
                """
                INSERT INTO snapshots (
                    snapshot_id,
                    tenant_id,
                    entity_type,
                    entity_id,
                    entity_version,
                    payload_json,
                    payload_hash,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.tenant_id,
                    snapshot.entity_type,
                    snapshot.entity_id,
                    snapshot.entity_version,
                    canonical_json(
                        snapshot.payload
                    ),
                    snapshot.payload_hash,
                    _dt(
                        snapshot.created_at
                    ),
                ),
            )

        return snapshot

    def latest_snapshot(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
    ) -> Snapshot | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM snapshots
            WHERE tenant_id = ?
              AND entity_type = ?
              AND entity_id = ?
            ORDER BY entity_version DESC,
                     created_at DESC
            LIMIT 1
            """,
            (
                tenant_id,
                entity_type,
                entity_id,
            ),
        ).fetchone()

        if row is None:
            return None

        payload = json.loads(
            row["payload_json"]
        )

        if (
            payload_hash(
                payload
            )
            != row["payload_hash"]
        ):
            raise DataIntegrityError(
                "snapshot integrity failure"
            )

        return Snapshot(
            snapshot_id=(
                row["snapshot_id"]
            ),
            tenant_id=(
                row["tenant_id"]
            ),
            entity_type=(
                row["entity_type"]
            ),
            entity_id=(
                row["entity_id"]
            ),
            entity_version=int(
                row[
                    "entity_version"
                ]
            ),
            payload=payload,
            payload_hash=(
                row["payload_hash"]
            ),
            created_at=_parse_dt(
                row["created_at"]
            ),
        )

    # ========================================================
    # BACKUP / RESTORE VERIFICATION
    # ========================================================

    def backup(
        self,
        destination: str | Path,
    ) -> BackupResult:
        destination = Path(
            destination
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if destination.exists():
            destination.unlink()

        target = sqlite3.connect(
            str(
                destination
            )
        )

        try:
            with self._lock:
                self._connection.backup(
                    target
                )

        finally:
            target.close()

        raw = destination.read_bytes()

        digest = hashlib.sha256(
            raw
        ).hexdigest()

        return BackupResult(
            path=str(
                destination
            ),
            sha256=digest,
            size_bytes=len(
                raw
            ),
            created_at=utcnow(),
        )

    @staticmethod
    def verify_backup(
        path: str | Path,
        *,
        expected_sha256: str | None = None,
    ) -> bool:
        path = Path(
            path
        )

        if not path.is_file():
            raise DataIntegrityError(
                "backup file missing"
            )

        raw = path.read_bytes()

        digest = hashlib.sha256(
            raw
        ).hexdigest()

        if (
            expected_sha256 is not None
            and digest
            != expected_sha256
        ):
            raise DataIntegrityError(
                "backup checksum mismatch"
            )

        db = sqlite3.connect(
            str(
                path
            )
        )

        try:
            result = db.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

        finally:
            db.close()

        if result != "ok":
            raise DataIntegrityError(
                "backup integrity_check failed"
            )

        return True

    # ========================================================
    # HEALTH
    # ========================================================

    def health(
        self,
    ) -> PersistenceHealth:
        integrity = (
            self._connection
            .execute(
                "PRAGMA integrity_check"
            )
            .fetchone()[0]
        )

        quick = (
            self._connection
            .execute(
                "PRAGMA quick_check"
            )
            .fetchone()[0]
        )

        journal = (
            self._connection
            .execute(
                "PRAGMA journal_mode"
            )
            .fetchone()[0]
        )

        entity_count = int(
            self._connection.execute(
                """
                SELECT COUNT(*)
                FROM entities
                """
            ).fetchone()[0]
        )

        event_count = int(
            self._connection.execute(
                """
                SELECT COUNT(*)
                FROM durable_events
                """
            ).fetchone()[0]
        )

        pending = int(
            self._connection.execute(
                """
                SELECT COUNT(*)
                FROM outbox
                WHERE status IN (?, ?, ?)
                """,
                (
                    OutboxStatus
                    .PENDING
                    .value,
                    OutboxStatus
                    .FAILED
                    .value,
                    OutboxStatus
                    .CLAIMED
                    .value,
                ),
            ).fetchone()[0]
        )

        return PersistenceHealth(
            integrity_ok=(
                integrity
                == "ok"
            ),
            quick_check_ok=(
                quick
                == "ok"
            ),
            journal_mode=str(
                journal
            ).lower(),
            schema_version=(
                self.schema_version()
            ),
            entity_count=(
                entity_count
            ),
            event_count=(
                event_count
            ),
            pending_outbox_count=(
                pending
            ),
        )
