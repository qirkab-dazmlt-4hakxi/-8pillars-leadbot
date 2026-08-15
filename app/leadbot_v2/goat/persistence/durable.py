from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


# ============================================================
# ERRORS
# ============================================================


class PersistenceError(RuntimeError):
    pass


class OptimisticConcurrencyError(PersistenceError):
    pass


class PersistenceIntegrityError(PersistenceError):
    pass


class IdempotencyConflict(PersistenceError):
    pass


class MigrationDriftError(PersistenceError):
    pass


class OutboxLeaseError(PersistenceError):
    pass


class InboxConflict(PersistenceError):
    pass


class SnapshotIntegrityError(PersistenceError):
    pass


class BackupIntegrityError(PersistenceError):
    pass


# ============================================================
# ENUMS
# ============================================================


class OutboxState(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRY = "retry"
    SENT = "sent"
    DEAD = "dead"


class IdempotencyState(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# ============================================================
# DATA MODELS
# ============================================================


@dataclass(frozen=True)
class PendingEvent:
    event_type: str
    payload: dict[str, Any]
    topic: str


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    tenant_id: str
    stream_id: str
    version: int
    event_type: str
    payload: dict[str, Any]
    payload_hash: str
    actor_id: str
    device_id: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class OutboxRecord:
    outbox_id: str
    tenant_id: str
    topic: str
    aggregate_id: str
    event_id: str
    payload: dict[str, Any]
    payload_hash: str
    state: OutboxState
    attempts: int
    available_at: datetime
    lease_owner: str | None
    lease_until: datetime | None
    created_at: datetime
    sent_at: datetime | None


@dataclass(frozen=True)
class IdempotencyResult:
    existing: bool
    completed: bool
    response: dict[str, Any] | None


@dataclass(frozen=True)
class SnapshotRecord:
    tenant_id: str
    stream_id: str
    version: int
    payload: dict[str, Any]
    payload_hash: str
    updated_at: datetime


@dataclass(frozen=True)
class BackupManifest:
    path: str
    sha256: str
    created_at: datetime
    event_count: int
    pending_outbox_count: int
    migration_versions: tuple[str, ...]


@dataclass(frozen=True)
class PersistenceHealth:
    journal_mode: str
    integrity: str
    event_count: int
    stream_count: int
    pending_outbox_count: int
    dead_outbox_count: int
    idempotency_count: int
    snapshot_count: int


# ============================================================
# UTILITY
# ============================================================


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex


def _required(value: Any, field: str) -> str:
    result = str(value or "").strip()

    if not result:
        raise ValueError(
            f"{field} is required"
        )

    return result


def _stable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(k): _stable(v)
            for k, v
            in sorted(value.items())
        }

    if isinstance(
        value,
        (tuple, list, set, frozenset),
    ):
        return [
            _stable(item)
            for item
            in value
        ]

    if hasattr(value, "__dict__"):
        return {
            k: _stable(v)
            for k, v
            in sorted(
                vars(value).items()
            )
            if not k.startswith("_")
        }

    return value


def _json(value: Any) -> str:
    return json.dumps(
        _stable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(
        _json(value).encode(
            "utf-8"
        )
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as fh:
        while True:
            chunk = fh.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def _dt(value: str | None) -> datetime | None:
    if value is None:
        return None

    return datetime.fromisoformat(
        value
    )


# ============================================================
# DATABASE MIGRATIONS
# ============================================================


MIGRATIONS: tuple[
    tuple[str, tuple[str, ...]],
    ...
] = (
    (
        "001_durable_core",
        (
            """
            CREATE TABLE IF NOT EXISTS goat_events (
                tenant_id TEXT NOT NULL,
                stream_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                device_id TEXT,
                occurred_at TEXT NOT NULL,
                PRIMARY KEY (
                    tenant_id,
                    stream_id,
                    version
                )
            )
            """,

            """
            CREATE INDEX IF NOT EXISTS
            idx_goat_events_stream
            ON goat_events (
                tenant_id,
                stream_id,
                version
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS goat_outbox (
                outbox_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at TEXT NOT NULL,
                lease_owner TEXT,
                lease_until TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT
            )
            """,

            """
            CREATE INDEX IF NOT EXISTS
            idx_goat_outbox_delivery
            ON goat_outbox (
                state,
                available_at,
                lease_until
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS goat_idempotency (
                tenant_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                response_json TEXT,
                state TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (
                    tenant_id,
                    scope,
                    idempotency_key
                )
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS goat_inbox (
                tenant_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                PRIMARY KEY (
                    tenant_id,
                    message_id
                )
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS goat_snapshots (
                tenant_id TEXT NOT NULL,
                stream_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (
                    tenant_id,
                    stream_id
                )
            )
            """,
        ),
    ),
)


# ============================================================
# DURABLE STORE
# ============================================================


class DurableStore:
    """
    Durable GOAT persistence contract.

    SQLite is used here as the battle-test adapter for transactional
    semantics. Production PostgreSQL must preserve these invariants:

      * tenant isolation
      * optimistic stream concurrency
      * append-only domain events
      * atomic event + outbox persistence
      * durable idempotency
      * durable inbox deduplication
      * hash-verified snapshots
      * migration checksum enforcement
      * leased outbox delivery
      * verified backups
    """

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(path)

        if str(self.path) != ":memory:":
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

        self._conn = sqlite3.connect(
            str(self.path),
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )

        self._conn.row_factory = (
            sqlite3.Row
        )

        self._configure()
        self.initialize()

    def _configure(self) -> None:
        self._conn.execute(
            "PRAGMA foreign_keys=ON"
        )

        self._conn.execute(
            "PRAGMA busy_timeout=30000"
        )

        if str(self.path) != ":memory:":
            self._conn.execute(
                "PRAGMA journal_mode=WAL"
            )

            self._conn.execute(
                "PRAGMA synchronous=FULL"
            )

        else:
            self._conn.execute(
                "PRAGMA synchronous=FULL"
            )

    @contextmanager
    def transaction(self):
        try:
            self._conn.execute(
                "BEGIN IMMEDIATE"
            )

            yield self._conn

            self._conn.execute(
                "COMMIT"
            )

        except Exception:
            try:
                self._conn.execute(
                    "ROLLBACK"
                )

            except sqlite3.Error:
                pass

            raise

    def close(self) -> None:
        self._conn.close()

    def initialize(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goat_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )

        for version, statements in MIGRATIONS:
            checksum = _hash(
                list(statements)
            )

            existing = (
                self._conn.execute(
                    """
                    SELECT checksum
                    FROM goat_migrations
                    WHERE version = ?
                    """,
                    (version,),
                ).fetchone()
            )

            if existing is not None:
                if (
                    existing["checksum"]
                    != checksum
                ):
                    raise MigrationDriftError(
                        (
                            "migration checksum mismatch: "
                            + version
                        )
                    )

                continue

            with self.transaction() as tx:
                for statement in statements:
                    tx.execute(
                        statement
                    )

                tx.execute(
                    """
                    INSERT INTO goat_migrations (
                        version,
                        checksum,
                        applied_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        version,
                        checksum,
                        _now().isoformat(),
                    ),
                )

    # ========================================================
    # EVENT STORE
    # ========================================================

    def current_version(
        self,
        *,
        tenant_id: str,
        stream_id: str,
    ) -> int:
        row = self._conn.execute(
            """
            SELECT COALESCE(
                MAX(version),
                0
            ) AS version
            FROM goat_events
            WHERE tenant_id = ?
              AND stream_id = ?
            """,
            (
                tenant_id,
                stream_id,
            ),
        ).fetchone()

        return int(
            row["version"]
        )

    def append(
        self,
        *,
        tenant_id: str,
        stream_id: str,
        expected_version: int,
        event_type: str,
        payload: dict[str, Any],
        topic: str,
        actor_id: str,
        device_id: str | None = None,
    ) -> EventEnvelope:
        results = self.append_many(
            tenant_id=tenant_id,
            stream_id=stream_id,
            expected_version=(
                expected_version
            ),
            events=(
                PendingEvent(
                    event_type=event_type,
                    payload=payload,
                    topic=topic,
                ),
            ),
            actor_id=actor_id,
            device_id=device_id,
        )

        return results[0]

    def append_many(
        self,
        *,
        tenant_id: str,
        stream_id: str,
        expected_version: int,
        events: Iterable[
            PendingEvent
        ],
        actor_id: str,
        device_id: str | None = None,
    ) -> tuple[
        EventEnvelope,
        ...
    ]:
        tenant_id = _required(
            tenant_id,
            "tenant_id",
        )

        stream_id = _required(
            stream_id,
            "stream_id",
        )

        actor_id = _required(
            actor_id,
            "actor_id",
        )

        if expected_version < 0:
            raise ValueError(
                "expected_version cannot be negative"
            )

        pending = tuple(
            events
        )

        if not pending:
            raise ValueError(
                "at least one event is required"
            )

        envelopes = []

        with self.transaction() as tx:
            row = tx.execute(
                """
                SELECT COALESCE(
                    MAX(version),
                    0
                ) AS version
                FROM goat_events
                WHERE tenant_id = ?
                  AND stream_id = ?
                """,
                (
                    tenant_id,
                    stream_id,
                ),
            ).fetchone()

            actual_version = int(
                row["version"]
            )

            if (
                actual_version
                != expected_version
            ):
                raise (
                    OptimisticConcurrencyError(
                        (
                            "stream version conflict: "
                            f"expected={expected_version} "
                            f"actual={actual_version}"
                        )
                    )
                )

            next_version = (
                actual_version
                + 1
            )

            for pending_event in pending:
                event_type = _required(
                    pending_event.event_type,
                    "event_type",
                )

                topic = _required(
                    pending_event.topic,
                    "topic",
                )

                occurred_at = _now()

                event_id = _id(
                    "evt"
                )

                payload_json = _json(
                    pending_event.payload
                )

                payload_hash = _hash(
                    pending_event.payload
                )

                tx.execute(
                    """
                    INSERT INTO goat_events (
                        tenant_id,
                        stream_id,
                        version,
                        event_id,
                        event_type,
                        payload_json,
                        payload_hash,
                        actor_id,
                        device_id,
                        occurred_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?
                    )
                    """,
                    (
                        tenant_id,
                        stream_id,
                        next_version,
                        event_id,
                        event_type,
                        payload_json,
                        payload_hash,
                        actor_id,
                        device_id,
                        occurred_at.isoformat(),
                    ),
                )

                outbox_id = _id(
                    "out"
                )

                tx.execute(
                    """
                    INSERT INTO goat_outbox (
                        outbox_id,
                        tenant_id,
                        topic,
                        aggregate_id,
                        event_id,
                        payload_json,
                        payload_hash,
                        state,
                        attempts,
                        available_at,
                        lease_owner,
                        lease_until,
                        created_at,
                        sent_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, 0, ?, NULL,
                        NULL, ?, NULL
                    )
                    """,
                    (
                        outbox_id,
                        tenant_id,
                        topic,
                        stream_id,
                        event_id,
                        payload_json,
                        payload_hash,
                        OutboxState
                        .PENDING
                        .value,
                        occurred_at.isoformat(),
                        occurred_at.isoformat(),
                    ),
                )

                envelopes.append(
                    EventEnvelope(
                        event_id=event_id,
                        tenant_id=tenant_id,
                        stream_id=stream_id,
                        version=next_version,
                        event_type=event_type,
                        payload=dict(
                            pending_event.payload
                        ),
                        payload_hash=payload_hash,
                        actor_id=actor_id,
                        device_id=device_id,
                        occurred_at=occurred_at,
                    )
                )

                next_version += 1

        return tuple(
            envelopes
        )

    def read_stream(
        self,
        *,
        tenant_id: str,
        stream_id: str,
        after_version: int = 0,
        limit: int = 1000,
    ) -> tuple[
        EventEnvelope,
        ...
    ]:
        if limit <= 0:
            raise ValueError(
                "limit must be positive"
            )

        rows = self._conn.execute(
            """
            SELECT *
            FROM goat_events
            WHERE tenant_id = ?
              AND stream_id = ?
              AND version > ?
            ORDER BY version ASC
            LIMIT ?
            """,
            (
                tenant_id,
                stream_id,
                after_version,
                limit,
            ),
        ).fetchall()

        result = []

        for row in rows:
            payload = json.loads(
                row["payload_json"]
            )

            calculated = _hash(
                payload
            )

            if (
                calculated
                != row["payload_hash"]
            ):
                raise PersistenceIntegrityError(
                    (
                        "event payload integrity "
                        "verification failed"
                    )
                )

            result.append(
                EventEnvelope(
                    event_id=(
                        row["event_id"]
                    ),
                    tenant_id=(
                        row["tenant_id"]
                    ),
                    stream_id=(
                        row["stream_id"]
                    ),
                    version=int(
                        row["version"]
                    ),
                    event_type=(
                        row["event_type"]
                    ),
                    payload=payload,
                    payload_hash=(
                        row["payload_hash"]
                    ),
                    actor_id=(
                        row["actor_id"]
                    ),
                    device_id=(
                        row["device_id"]
                    ),
                    occurred_at=(
                        datetime.fromisoformat(
                            row[
                                "occurred_at"
                            ]
                        )
                    ),
                )
            )

        return tuple(
            result
        )

    # ========================================================
    # IDEMPOTENCY
    # ========================================================

    def begin_idempotent(
        self,
        *,
        tenant_id: str,
        scope: str,
        key: str,
        request: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> IdempotencyResult:
        if ttl_seconds <= 0:
            raise ValueError(
                "ttl_seconds must be positive"
            )

        tenant_id = _required(
            tenant_id,
            "tenant_id",
        )

        scope = _required(
            scope,
            "scope",
        )

        key = _required(
            key,
            "key",
        )

        request_hash = _hash(
            request
        )

        now = _now()

        expires_at = (
            now
            + timedelta(
                seconds=ttl_seconds
            )
        )

        with self.transaction() as tx:
            row = tx.execute(
                """
                SELECT *
                FROM goat_idempotency
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

            if row is not None:
                if (
                    row["request_hash"]
                    != request_hash
                ):
                    raise IdempotencyConflict(
                        (
                            "idempotency key reused "
                            "with different request"
                        )
                    )

                response = (
                    json.loads(
                        row[
                            "response_json"
                        ]
                    )
                    if row[
                        "response_json"
                    ]
                    else None
                )

                return IdempotencyResult(
                    existing=True,
                    completed=(
                        row["state"]
                        == IdempotencyState
                        .COMPLETED
                        .value
                    ),
                    response=response,
                )

            tx.execute(
                """
                INSERT INTO goat_idempotency (
                    tenant_id,
                    scope,
                    idempotency_key,
                    request_hash,
                    response_json,
                    state,
                    expires_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, NULL,
                    ?, ?, ?, ?
                )
                """,
                (
                    tenant_id,
                    scope,
                    key,
                    request_hash,
                    IdempotencyState
                    .IN_PROGRESS
                    .value,
                    expires_at.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

        return IdempotencyResult(
            existing=False,
            completed=False,
            response=None,
        )

    def complete_idempotent(
        self,
        *,
        tenant_id: str,
        scope: str,
        key: str,
        response: dict[str, Any],
    ) -> None:
        with self.transaction() as tx:
            cursor = tx.execute(
                """
                UPDATE goat_idempotency
                SET response_json = ?,
                    state = ?,
                    updated_at = ?
                WHERE tenant_id = ?
                  AND scope = ?
                  AND idempotency_key = ?
                """,
                (
                    _json(response),
                    IdempotencyState
                    .COMPLETED
                    .value,
                    _now().isoformat(),
                    tenant_id,
                    scope,
                    key,
                ),
            )

            if cursor.rowcount != 1:
                raise KeyError(
                    (
                        tenant_id,
                        scope,
                        key,
                    )
                )

    # ========================================================
    # INBOX DEDUPLICATION
    # ========================================================

    def register_inbox_message(
        self,
        *,
        tenant_id: str,
        message_id: str,
        payload: dict[str, Any],
    ) -> bool:
        payload_hash = _hash(
            payload
        )

        with self.transaction() as tx:
            row = tx.execute(
                """
                SELECT payload_hash
                FROM goat_inbox
                WHERE tenant_id = ?
                  AND message_id = ?
                """,
                (
                    tenant_id,
                    message_id,
                ),
            ).fetchone()

            if row is not None:
                if (
                    row["payload_hash"]
                    != payload_hash
                ):
                    raise InboxConflict(
                        (
                            "message id reused "
                            "with different payload"
                        )
                    )

                return False

            tx.execute(
                """
                INSERT INTO goat_inbox (
                    tenant_id,
                    message_id,
                    payload_hash,
                    processed_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    message_id,
                    payload_hash,
                    _now().isoformat(),
                ),
            )

        return True

    # ========================================================
    # SNAPSHOTS
    # ========================================================

    def save_snapshot(
        self,
        *,
        tenant_id: str,
        stream_id: str,
        version: int,
        payload: dict[str, Any],
    ) -> SnapshotRecord:
        if version < 0:
            raise ValueError(
                "version cannot be negative"
            )

        payload_json = _json(
            payload
        )

        payload_hash = _hash(
            payload
        )

        now = _now()

        with self.transaction() as tx:
            current = tx.execute(
                """
                SELECT version
                FROM goat_snapshots
                WHERE tenant_id = ?
                  AND stream_id = ?
                """,
                (
                    tenant_id,
                    stream_id,
                ),
            ).fetchone()

            if (
                current is not None
                and version
                < int(
                    current["version"]
                )
            ):
                raise OptimisticConcurrencyError(
                    (
                        "cannot replace snapshot "
                        "with older version"
                    )
                )

            tx.execute(
                """
                INSERT INTO goat_snapshots (
                    tenant_id,
                    stream_id,
                    version,
                    payload_json,
                    payload_hash,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (
                    tenant_id,
                    stream_id
                )
                DO UPDATE SET
                    version = excluded.version,
                    payload_json = excluded.payload_json,
                    payload_hash = excluded.payload_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    tenant_id,
                    stream_id,
                    version,
                    payload_json,
                    payload_hash,
                    now.isoformat(),
                ),
            )

        return SnapshotRecord(
            tenant_id=tenant_id,
            stream_id=stream_id,
            version=version,
            payload=dict(payload),
            payload_hash=payload_hash,
            updated_at=now,
        )

    def load_snapshot(
        self,
        *,
        tenant_id: str,
        stream_id: str,
    ) -> SnapshotRecord | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM goat_snapshots
            WHERE tenant_id = ?
              AND stream_id = ?
            """,
            (
                tenant_id,
                stream_id,
            ),
        ).fetchone()

        if row is None:
            return None

        payload = json.loads(
            row["payload_json"]
        )

        if (
            _hash(payload)
            != row["payload_hash"]
        ):
            raise SnapshotIntegrityError(
                "snapshot integrity failure"
            )

        return SnapshotRecord(
            tenant_id=(
                row["tenant_id"]
            ),
            stream_id=(
                row["stream_id"]
            ),
            version=int(
                row["version"]
            ),
            payload=payload,
            payload_hash=(
                row["payload_hash"]
            ),
            updated_at=(
                datetime.fromisoformat(
                    row["updated_at"]
                )
            ),
        )

    # ========================================================
    # TRANSACTIONAL OUTBOX
    # ========================================================

    def claim_outbox(
        self,
        *,
        worker_id: str,
        limit: int = 50,
        lease_seconds: int = 60,
        as_of: datetime | None = None,
    ) -> tuple[
        OutboxRecord,
        ...
    ]:
        worker_id = _required(
            worker_id,
            "worker_id",
        )

        if limit <= 0:
            raise ValueError(
                "limit must be positive"
            )

        if lease_seconds <= 0:
            raise ValueError(
                "lease_seconds must be positive"
            )

        now = (
            as_of
            or _now()
        )

        lease_until = (
            now
            + timedelta(
                seconds=lease_seconds
            )
        )

        claimed_ids = []

        with self.transaction() as tx:
            rows = tx.execute(
                """
                SELECT outbox_id
                FROM goat_outbox
                WHERE state IN (?, ?)
                  AND available_at <= ?
                  AND (
                        lease_until IS NULL
                        OR lease_until <= ?
                  )
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (
                    OutboxState.PENDING.value,
                    OutboxState.RETRY.value,
                    now.isoformat(),
                    now.isoformat(),
                    limit,
                ),
            ).fetchall()

            for row in rows:
                outbox_id = (
                    row["outbox_id"]
                )

                cursor = tx.execute(
                    """
                    UPDATE goat_outbox
                    SET state = ?,
                        attempts = attempts + 1,
                        lease_owner = ?,
                        lease_until = ?
                    WHERE outbox_id = ?
                      AND (
                            lease_until IS NULL
                            OR lease_until <= ?
                      )
                    """,
                    (
                        OutboxState
                        .PROCESSING
                        .value,
                        worker_id,
                        lease_until.isoformat(),
                        outbox_id,
                        now.isoformat(),
                    ),
                )

                if cursor.rowcount == 1:
                    claimed_ids.append(
                        outbox_id
                    )

        return tuple(
            self._outbox_record(
                outbox_id
            )
            for outbox_id
            in claimed_ids
        )

    def _outbox_record(
        self,
        outbox_id: str,
    ) -> OutboxRecord:
        row = self._conn.execute(
            """
            SELECT *
            FROM goat_outbox
            WHERE outbox_id = ?
            """,
            (outbox_id,),
        ).fetchone()

        if row is None:
            raise KeyError(
                outbox_id
            )

        payload = json.loads(
            row["payload_json"]
        )

        if (
            _hash(payload)
            != row["payload_hash"]
        ):
            raise PersistenceIntegrityError(
                "outbox payload integrity failure"
            )

        return OutboxRecord(
            outbox_id=(
                row["outbox_id"]
            ),
            tenant_id=(
                row["tenant_id"]
            ),
            topic=(
                row["topic"]
            ),
            aggregate_id=(
                row["aggregate_id"]
            ),
            event_id=(
                row["event_id"]
            ),
            payload=payload,
            payload_hash=(
                row["payload_hash"]
            ),
            state=(
                OutboxState(
                    row["state"]
                )
            ),
            attempts=int(
                row["attempts"]
            ),
            available_at=(
                datetime.fromisoformat(
                    row["available_at"]
                )
            ),
            lease_owner=(
                row["lease_owner"]
            ),
            lease_until=(
                _dt(
                    row["lease_until"]
                )
            ),
            created_at=(
                datetime.fromisoformat(
                    row["created_at"]
                )
            ),
            sent_at=(
                _dt(
                    row["sent_at"]
                )
            ),
        )

    def acknowledge_outbox(
        self,
        *,
        outbox_id: str,
        worker_id: str,
    ) -> OutboxRecord:
        now = _now()

        with self.transaction() as tx:
            cursor = tx.execute(
                """
                UPDATE goat_outbox
                SET state = ?,
                    sent_at = ?,
                    lease_owner = NULL,
                    lease_until = NULL
                WHERE outbox_id = ?
                  AND state = ?
                  AND lease_owner = ?
                """,
                (
                    OutboxState.SENT.value,
                    now.isoformat(),
                    outbox_id,
                    OutboxState
                    .PROCESSING
                    .value,
                    worker_id,
                ),
            )

            if cursor.rowcount != 1:
                raise OutboxLeaseError(
                    (
                        "worker does not own "
                        "active outbox lease"
                    )
                )

        return self._outbox_record(
            outbox_id
        )

    def fail_outbox(
        self,
        *,
        outbox_id: str,
        worker_id: str,
        retry_delay_seconds: int = 30,
        max_attempts: int = 8,
    ) -> OutboxRecord:
        if retry_delay_seconds < 0:
            raise ValueError(
                (
                    "retry_delay_seconds "
                    "cannot be negative"
                )
            )

        current = self._outbox_record(
            outbox_id
        )

        if (
            current.state
            != OutboxState.PROCESSING
            or current.lease_owner
            != worker_id
        ):
            raise OutboxLeaseError(
                "worker does not own lease"
            )

        next_state = (
            OutboxState.DEAD
            if current.attempts
            >= max_attempts
            else OutboxState.RETRY
        )

        available_at = (
            _now()
            + timedelta(
                seconds=(
                    retry_delay_seconds
                )
            )
        )

        with self.transaction() as tx:
            tx.execute(
                """
                UPDATE goat_outbox
                SET state = ?,
                    available_at = ?,
                    lease_owner = NULL,
                    lease_until = NULL
                WHERE outbox_id = ?
                """,
                (
                    next_state.value,
                    available_at.isoformat(),
                    outbox_id,
                ),
            )

        return self._outbox_record(
            outbox_id
        )

    # ========================================================
    # HEALTH + BACKUP
    # ========================================================

    def migrations(
        self,
    ) -> tuple[str, ...]:
        rows = self._conn.execute(
            """
            SELECT version
            FROM goat_migrations
            ORDER BY version
            """
        ).fetchall()

        return tuple(
            row["version"]
            for row in rows
        )

    def health(
        self,
    ) -> PersistenceHealth:
        integrity = (
            self._conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        journal = (
            self._conn.execute(
                "PRAGMA journal_mode"
            ).fetchone()[0]
        )

        def scalar(
            sql: str,
        ) -> int:
            return int(
                self._conn.execute(
                    sql
                ).fetchone()[0]
            )

        return PersistenceHealth(
            journal_mode=str(
                journal
            ).lower(),
            integrity=str(
                integrity
            ).lower(),
            event_count=scalar(
                "SELECT COUNT(*) "
                "FROM goat_events"
            ),
            stream_count=scalar(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT tenant_id,
                           stream_id
                    FROM goat_events
                    GROUP BY tenant_id,
                             stream_id
                )
                """
            ),
            pending_outbox_count=scalar(
                """
                SELECT COUNT(*)
                FROM goat_outbox
                WHERE state IN (
                    'pending',
                    'retry',
                    'processing'
                )
                """
            ),
            dead_outbox_count=scalar(
                """
                SELECT COUNT(*)
                FROM goat_outbox
                WHERE state = 'dead'
                """
            ),
            idempotency_count=scalar(
                """
                SELECT COUNT(*)
                FROM goat_idempotency
                """
            ),
            snapshot_count=scalar(
                """
                SELECT COUNT(*)
                FROM goat_snapshots
                """
            ),
        )

    def create_backup(
        self,
        destination: str | Path,
    ) -> BackupManifest:
        destination = Path(
            destination
        )

        if destination.exists():
            raise FileExistsError(
                destination
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target = sqlite3.connect(
            str(destination)
        )

        try:
            self._conn.backup(
                target
            )

            target.commit()

            integrity = (
                target.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            )

            if (
                str(integrity).lower()
                != "ok"
            ):
                raise BackupIntegrityError(
                    (
                        "backup integrity_check "
                        "did not return ok"
                    )
                )

        finally:
            target.close()

        health = self.health()

        manifest = BackupManifest(
            path=str(
                destination
            ),
            sha256=(
                _file_sha256(
                    destination
                )
            ),
            created_at=_now(),
            event_count=(
                health.event_count
            ),
            pending_outbox_count=(
                health
                .pending_outbox_count
            ),
            migration_versions=(
                self.migrations()
            ),
        )

        return manifest

    @staticmethod
    def verify_backup(
        manifest: BackupManifest,
    ) -> bool:
        path = Path(
            manifest.path
        )

        if not path.exists():
            raise BackupIntegrityError(
                "backup file missing"
            )

        actual_sha = (
            _file_sha256(
                path
            )
        )

        if (
            actual_sha
            != manifest.sha256
        ):
            raise BackupIntegrityError(
                "backup checksum mismatch"
            )

        conn = sqlite3.connect(
            str(path)
        )

        try:
            integrity = conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            if (
                str(integrity).lower()
                != "ok"
            ):
                raise BackupIntegrityError(
                    "backup database is corrupt"
                )

            event_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM goat_events
                    """
                ).fetchone()[0]
            )

            if (
                event_count
                != manifest.event_count
            ):
                raise BackupIntegrityError(
                    "backup event count mismatch"
                )

            migrations = tuple(
                row[0]
                for row
                in conn.execute(
                    """
                    SELECT version
                    FROM goat_migrations
                    ORDER BY version
                    """
                ).fetchall()
            )

            if (
                migrations
                != manifest
                .migration_versions
            ):
                raise BackupIntegrityError(
                    (
                        "backup migration "
                        "manifest mismatch"
                    )
                )

        finally:
            conn.close()

        return True
