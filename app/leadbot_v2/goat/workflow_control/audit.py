from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .models import (
    normalize_time,
    stable_hash,
)


class AuditIntegrityError(RuntimeError):
    pass


@dataclass
class AuditEntry:
    sequence: int

    workflow_id: str
    tenant_id: str

    event_type: str
    actor_id: str

    payload: dict[str, Any]

    occurred_at: datetime

    previous_hash: str
    entry_hash: str


class HashChainJournal:
    GENESIS = "0" * 64

    def __init__(self) -> None:
        self._entries: list[
            AuditEntry
        ] = []

    def append(
        self,
        *,
        workflow_id: str,
        tenant_id: str,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
        occurred_at=None,
    ) -> AuditEntry:
        timestamp = normalize_time(
            occurred_at
        )

        sequence = (
            len(self._entries) + 1
        )

        previous_hash = (
            self._entries[-1].entry_hash
            if self._entries
            else self.GENESIS
        )

        body = {
            "sequence":
                sequence,
            "workflow_id":
                workflow_id,
            "tenant_id":
                tenant_id,
            "event_type":
                event_type,
            "actor_id":
                actor_id,
            "payload":
                deepcopy(payload),
            "occurred_at":
                timestamp,
            "previous_hash":
                previous_hash,
        }

        entry_hash = stable_hash(
            body
        )

        entry = AuditEntry(
            sequence=sequence,
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            event_type=event_type,
            actor_id=actor_id,
            payload=deepcopy(
                payload
            ),
            occurred_at=timestamp,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )

        self._entries.append(
            entry
        )

        return deepcopy(
            entry
        )

    def verify(self) -> bool:
        previous_hash = (
            self.GENESIS
        )

        for expected_sequence, entry in enumerate(
            self._entries,
            start=1,
        ):
            if (
                entry.sequence
                != expected_sequence
            ):
                raise AuditIntegrityError(
                    "audit sequence discontinuity"
                )

            if (
                entry.previous_hash
                != previous_hash
            ):
                raise AuditIntegrityError(
                    "audit hash-chain discontinuity"
                )

            calculated = stable_hash(
                {
                    "sequence":
                        entry.sequence,
                    "workflow_id":
                        entry.workflow_id,
                    "tenant_id":
                        entry.tenant_id,
                    "event_type":
                        entry.event_type,
                    "actor_id":
                        entry.actor_id,
                    "payload":
                        entry.payload,
                    "occurred_at":
                        entry.occurred_at,
                    "previous_hash":
                        entry.previous_hash,
                }
            )

            if (
                calculated
                != entry.entry_hash
            ):
                raise AuditIntegrityError(
                    "audit entry tampered"
                )

            previous_hash = (
                entry.entry_hash
            )

        return True

    def entries(
        self,
    ) -> list[AuditEntry]:
        return deepcopy(
            self._entries
        )
