from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class PersistenceError(RuntimeError):
    pass


class PersistenceValidationError(PersistenceError):
    pass


class OptimisticConcurrencyError(PersistenceError):
    pass


class TenantIsolationError(PersistenceError):
    pass


class DataIntegrityError(PersistenceError):
    pass


class DuplicateMessageConflict(PersistenceError):
    pass


class IdempotencyConflict(PersistenceError):
    pass


class LeaseBusy(PersistenceError):
    pass


class LeaseLost(PersistenceError):
    pass


class OutboxStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD = "dead"


@dataclass(frozen=True)
class EntityRecord:
    tenant_id: str
    entity_type: str
    entity_id: str

    version: int

    payload: dict[str, Any]
    payload_hash: str

    created_at: datetime
    updated_at: datetime

    deleted_at: datetime | None


@dataclass(frozen=True)
class DurableEvent:
    sequence: int

    event_id: str

    tenant_id: str

    aggregate_type: str
    aggregate_id: str

    aggregate_version: int

    event_type: str
    actor_id: str

    payload: dict[str, Any]

    payload_hash: str

    previous_hash: str
    event_hash: str

    occurred_at: datetime


@dataclass(frozen=True)
class OutboxMessage:
    outbox_id: str

    tenant_id: str

    topic: str

    aggregate_type: str | None
    aggregate_id: str | None

    payload: dict[str, Any]
    payload_hash: str

    status: OutboxStatus

    attempts: int

    available_at: datetime

    locked_by: str | None
    lease_expires_at: datetime | None

    dedupe_key: str | None

    created_at: datetime


@dataclass(frozen=True)
class Lease:
    lease_name: str

    owner_id: str

    fencing_token: int

    expires_at: datetime


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str

    tenant_id: str

    entity_type: str
    entity_id: str

    entity_version: int

    payload: dict[str, Any]
    payload_hash: str

    created_at: datetime


@dataclass(frozen=True)
class BackupResult:
    path: str

    sha256: str

    size_bytes: int

    created_at: datetime


@dataclass(frozen=True)
class PersistenceHealth:
    integrity_ok: bool
    quick_check_ok: bool

    journal_mode: str

    schema_version: int

    entity_count: int
    event_count: int
    pending_outbox_count: int
