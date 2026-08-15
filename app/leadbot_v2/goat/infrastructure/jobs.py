from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class JobQueueError(RuntimeError):
    pass


class JobNotFound(JobQueueError):
    pass


class JobLeaseError(JobQueueError):
    pass


class JobIdempotencyConflict(JobQueueError):
    pass


class JobIntegrityError(JobQueueError):
    pass


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY = "retry"
    SUCCEEDED = "succeeded"
    DEAD = "dead"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Job:
    job_id: str
    tenant_id: str
    queue: str
    task_type: str
    idempotency_key: str
    payload: dict[str, Any]
    payload_hash: str
    state: JobState
    priority: int
    attempts: int
    max_attempts: int
    available_at: datetime
    lease_owner: str | None
    lease_until: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class QueueStats:
    pending: int
    running: int
    retry: int
    succeeded: int
    dead: int
    cancelled: int


def _now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _id(
    prefix: str,
) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def _required(
    value: Any,
    field: str,
) -> str:
    result = str(
        value
        or ""
    ).strip()

    if not result:
        raise ValueError(
            f"{field} is required"
        )

    return result


def _json(
    value: Any,
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
        default=str,
    )


def _hash(
    value: Any,
) -> str:
    return hashlib.sha256(
        _json(value).encode(
            "utf-8"
        )
    ).hexdigest()


def _dt(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    return datetime.fromisoformat(
        value
    )


class DurableJobQueue:
    """
    Durable leased work queue.

    The production distributed adapter can move to PostgreSQL or a managed
    queue system, but must preserve idempotency, lease ownership, retry,
    dead-letter, scheduling, priority and tenant semantics.
    """

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(
            path
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._conn = sqlite3.connect(
            str(
                self.path
            ),
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )

        self._conn.row_factory = (
            sqlite3.Row
        )

        self._conn.execute(
            "PRAGMA journal_mode=WAL"
        )

        self._conn.execute(
            "PRAGMA synchronous=FULL"
        )

        self._conn.execute(
            "PRAGMA busy_timeout=30000"
        )

        self._initialize()

    def close(
        self,
    ) -> None:
        self._conn.close()

    def _initialize(
        self,
    ) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goat_jobs (
                job_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                queue TEXT NOT NULL,
                task_type TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                state TEXT NOT NULL,
                priority INTEGER NOT NULL,
                attempts INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                available_at TEXT NOT NULL,
                lease_owner TEXT,
                lease_until TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                last_error TEXT,
                UNIQUE (
                    tenant_id,
                    queue,
                    idempotency_key
                )
            )
            """
        )

        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_goat_jobs_claim
            ON goat_jobs (
                queue,
                state,
                available_at,
                priority DESC,
                created_at
            )
            """
        )

    def _row(
        self,
        row: sqlite3.Row,
    ) -> Job:
        payload = json.loads(
            row["payload_json"]
        )

        if (
            _hash(payload)
            != row["payload_hash"]
        ):
            raise JobIntegrityError(
                "job payload integrity failure"
            )

        return Job(
            job_id=(
                row["job_id"]
            ),
            tenant_id=(
                row["tenant_id"]
            ),
            queue=(
                row["queue"]
            ),
            task_type=(
                row["task_type"]
            ),
            idempotency_key=(
                row[
                    "idempotency_key"
                ]
            ),
            payload=payload,
            payload_hash=(
                row["payload_hash"]
            ),
            state=(
                JobState(
                    row["state"]
                )
            ),
            priority=int(
                row["priority"]
            ),
            attempts=int(
                row["attempts"]
            ),
            max_attempts=int(
                row[
                    "max_attempts"
                ]
            ),
            available_at=(
                datetime.fromisoformat(
                    row[
                        "available_at"
                    ]
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
            updated_at=(
                datetime.fromisoformat(
                    row["updated_at"]
                )
            ),
            completed_at=(
                _dt(
                    row[
                        "completed_at"
                    ]
                )
            ),
            last_error=(
                row["last_error"]
            ),
        )

    def get(
        self,
        job_id: str,
    ) -> Job:
        row = self._conn.execute(
            """
            SELECT *
            FROM goat_jobs
            WHERE job_id = ?
            """,
            (
                job_id,
            ),
        ).fetchone()

        if row is None:
            raise JobNotFound(
                job_id
            )

        return self._row(
            row
        )

    def enqueue(
        self,
        *,
        tenant_id: str,
        queue: str,
        task_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
        priority: int = 0,
        max_attempts: int = 8,
        available_at: (
            datetime
            | None
        ) = None,
    ) -> Job:
        tenant_id = _required(
            tenant_id,
            "tenant_id",
        )

        queue = _required(
            queue,
            "queue",
        )

        task_type = _required(
            task_type,
            "task_type",
        )

        idempotency_key = (
            _required(
                idempotency_key,
                "idempotency_key",
            )
        )

        if max_attempts <= 0:
            raise ValueError(
                "max_attempts must be positive"
            )

        payload_hash = _hash(
            payload
        )

        existing = self._conn.execute(
            """
            SELECT *
            FROM goat_jobs
            WHERE tenant_id = ?
              AND queue = ?
              AND idempotency_key = ?
            """,
            (
                tenant_id,
                queue,
                idempotency_key,
            ),
        ).fetchone()

        if existing is not None:
            job = self._row(
                existing
            )

            if (
                job.payload_hash
                != payload_hash
                or job.task_type
                != task_type
            ):
                raise (
                    JobIdempotencyConflict(
                        (
                            "job idempotency key "
                            "reused with different work"
                        )
                    )
                )

            return job

        now = _now()

        scheduled = (
            available_at
            or now
        )

        if (
            scheduled.tzinfo
            is None
            or scheduled.utcoffset()
            is None
        ):
            raise ValueError(
                "available_at must be timezone-aware"
            )

        job_id = _id(
            "job"
        )

        self._conn.execute(
            """
            INSERT INTO goat_jobs (
                job_id,
                tenant_id,
                queue,
                task_type,
                idempotency_key,
                payload_json,
                payload_hash,
                state,
                priority,
                attempts,
                max_attempts,
                available_at,
                lease_owner,
                lease_until,
                created_at,
                updated_at,
                completed_at,
                last_error
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, 0, ?, ?,
                NULL, NULL, ?, ?,
                NULL, NULL
            )
            """,
            (
                job_id,
                tenant_id,
                queue,
                task_type,
                idempotency_key,
                _json(
                    payload
                ),
                payload_hash,
                JobState
                .PENDING
                .value,
                priority,
                max_attempts,
                scheduled.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )

        return self.get(
            job_id
        )

    def claim(
        self,
        *,
        queue: str,
        worker_id: str,
        limit: int = 10,
        lease_seconds: int = 120,
        as_of: (
            datetime
            | None
        ) = None,
    ) -> tuple[
        Job,
        ...
    ]:
        queue = _required(
            queue,
            "queue",
        )

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

        try:
            self._conn.execute(
                "BEGIN IMMEDIATE"
            )

            rows = self._conn.execute(
                """
                SELECT job_id
                FROM goat_jobs
                WHERE queue = ?
                  AND state IN (?, ?)
                  AND available_at <= ?
                  AND (
                        lease_until IS NULL
                        OR lease_until <= ?
                  )
                ORDER BY
                    priority DESC,
                    created_at ASC
                LIMIT ?
                """,
                (
                    queue,
                    JobState
                    .PENDING
                    .value,
                    JobState
                    .RETRY
                    .value,
                    now.isoformat(),
                    now.isoformat(),
                    limit,
                ),
            ).fetchall()

            claimed = []

            for row in rows:
                cursor = (
                    self._conn.execute(
                        """
                        UPDATE goat_jobs
                        SET state = ?,
                            attempts =
                                attempts + 1,
                            lease_owner = ?,
                            lease_until = ?,
                            updated_at = ?
                        WHERE job_id = ?
                          AND (
                                lease_until IS NULL
                                OR lease_until <= ?
                          )
                        """,
                        (
                            JobState
                            .RUNNING
                            .value,
                            worker_id,
                            lease_until
                            .isoformat(),
                            now.isoformat(),
                            row["job_id"],
                            now.isoformat(),
                        ),
                    )
                )

                if cursor.rowcount == 1:
                    claimed.append(
                        row["job_id"]
                    )

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

        return tuple(
            self.get(job_id)
            for job_id
            in claimed
        )

    def heartbeat(
        self,
        *,
        job_id: str,
        worker_id: str,
        extend_seconds: int = 120,
    ) -> Job:
        if extend_seconds <= 0:
            raise ValueError(
                "extend_seconds must be positive"
            )

        job = self.get(
            job_id
        )

        if (
            job.state
            != JobState.RUNNING
            or job.lease_owner
            != worker_id
        ):
            raise JobLeaseError(
                "worker does not own job lease"
            )

        now = _now()

        new_lease = (
            now
            + timedelta(
                seconds=extend_seconds
            )
        )

        self._conn.execute(
            """
            UPDATE goat_jobs
            SET lease_until = ?,
                updated_at = ?
            WHERE job_id = ?
              AND lease_owner = ?
              AND state = ?
            """,
            (
                new_lease.isoformat(),
                now.isoformat(),
                job_id,
                worker_id,
                JobState
                .RUNNING
                .value,
            ),
        )

        return self.get(
            job_id
        )

    def succeed(
        self,
        *,
        job_id: str,
        worker_id: str,
    ) -> Job:
        job = self.get(
            job_id
        )

        if (
            job.state
            != JobState.RUNNING
            or job.lease_owner
            != worker_id
        ):
            raise JobLeaseError(
                "worker does not own job lease"
            )

        now = _now()

        self._conn.execute(
            """
            UPDATE goat_jobs
            SET state = ?,
                lease_owner = NULL,
                lease_until = NULL,
                completed_at = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (
                JobState
                .SUCCEEDED
                .value,
                now.isoformat(),
                now.isoformat(),
                job_id,
            ),
        )

        return self.get(
            job_id
        )

    def fail(
        self,
        *,
        job_id: str,
        worker_id: str,
        error: str,
        retry_delay_seconds: int = 30,
    ) -> Job:
        job = self.get(
            job_id
        )

        if (
            job.state
            != JobState.RUNNING
            or job.lease_owner
            != worker_id
        ):
            raise JobLeaseError(
                "worker does not own job lease"
            )

        if retry_delay_seconds < 0:
            raise ValueError(
                "retry_delay_seconds cannot be negative"
            )

        next_state = (
            JobState.DEAD
            if job.attempts
            >= job.max_attempts
            else JobState.RETRY
        )

        available_at = (
            _now()
            + timedelta(
                seconds=(
                    retry_delay_seconds
                )
            )
        )

        self._conn.execute(
            """
            UPDATE goat_jobs
            SET state = ?,
                available_at = ?,
                lease_owner = NULL,
                lease_until = NULL,
                updated_at = ?,
                last_error = ?
            WHERE job_id = ?
            """,
            (
                next_state.value,
                available_at.isoformat(),
                _now().isoformat(),
                str(error)[
                    :4000
                ],
                job_id,
            ),
        )

        return self.get(
            job_id
        )

    def cancel(
        self,
        *,
        job_id: str,
    ) -> Job:
        job = self.get(
            job_id
        )

        if (
            job.state
            in {
                JobState.SUCCEEDED,
                JobState.DEAD,
            }
        ):
            raise JobQueueError(
                "terminal job cannot be cancelled"
            )

        self._conn.execute(
            """
            UPDATE goat_jobs
            SET state = ?,
                lease_owner = NULL,
                lease_until = NULL,
                updated_at = ?
            WHERE job_id = ?
            """,
            (
                JobState
                .CANCELLED
                .value,
                _now().isoformat(),
                job_id,
            ),
        )

        return self.get(
            job_id
        )

    def stats(
        self,
        *,
        queue: str,
    ) -> QueueStats:
        counts = {
            state:
                0
            for state
            in JobState
        }

        rows = self._conn.execute(
            """
            SELECT state,
                   COUNT(*) AS count
            FROM goat_jobs
            WHERE queue = ?
            GROUP BY state
            """,
            (
                queue,
            ),
        ).fetchall()

        for row in rows:
            counts[
                JobState(
                    row["state"]
                )
            ] = int(
                row["count"]
            )

        return QueueStats(
            pending=counts[
                JobState.PENDING
            ],
            running=counts[
                JobState.RUNNING
            ],
            retry=counts[
                JobState.RETRY
            ],
            succeeded=counts[
                JobState.SUCCEEDED
            ],
            dead=counts[
                JobState.DEAD
            ],
            cancelled=counts[
                JobState.CANCELLED
            ],
        )
