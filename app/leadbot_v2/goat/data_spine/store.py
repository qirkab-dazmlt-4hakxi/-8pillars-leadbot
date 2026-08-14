from __future__ import annotations

from dataclasses import replace
from typing import TypeVar

from leadbot_v2.goat.data_spine.models import (
    BaseEntity,
    SpineEvent,
    make_event,
    utc_now,
)


T = TypeVar("T", bound=BaseEntity)


class EntityNotFound(KeyError):
    pass


class TenantIsolationError(PermissionError):
    pass


class ConcurrencyConflict(RuntimeError):
    pass


class DataIntegrityError(RuntimeError):
    pass


class InMemoryDataSpine:
    """
    Prototype persistence for GOAT.

    Production target:
      PostgreSQL + row-level security + encrypted storage +
      durable event/outbox infrastructure.

    This prototype deliberately enforces:
      - tenant isolation
      - optimistic concurrency
      - immutable event history
      - per-aggregate event ordering
    """

    def __init__(self) -> None:
        self._entities: dict[str, BaseEntity] = {}
        self._events: list[SpineEvent] = []
        self._aggregate_sequence: dict[tuple[str, str], int] = {}

    def create(
        self,
        entity: T,
        *,
        actor_id: str,
        event_type: str,
        payload: dict | None = None,
        correlation_id: str | None = None,
    ) -> T:
        if entity.entity_id in self._entities:
            raise DataIntegrityError(
                f"duplicate entity: {entity.entity_id}"
            )

        self._entities[entity.entity_id] = entity

        self.append_event(
            tenant_id=entity.tenant_id,
            aggregate_type=type(entity).__name__,
            aggregate_id=entity.entity_id,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
            correlation_id=correlation_id,
        )

        return entity

    def get(
        self,
        *,
        entity_id: str,
        tenant_id: str,
        expected_type: type[T] | None = None,
    ) -> T:
        try:
            entity = self._entities[entity_id]
        except KeyError as exc:
            raise EntityNotFound(entity_id) from exc

        if entity.tenant_id != tenant_id:
            raise TenantIsolationError(
                "cross-tenant entity access denied"
            )

        if expected_type is not None and not isinstance(
            entity,
            expected_type,
        ):
            raise TypeError(
                f"{entity_id} is not {expected_type.__name__}"
            )

        return entity  # type: ignore[return-value]

    def update(
        self,
        entity: T,
        *,
        tenant_id: str,
        expected_version: int,
        actor_id: str,
        event_type: str,
        payload: dict | None = None,
        correlation_id: str | None = None,
    ) -> T:
        current = self.get(
            entity_id=entity.entity_id,
            tenant_id=tenant_id,
        )

        if current.version != expected_version:
            raise ConcurrencyConflict(
                f"expected version {expected_version}, "
                f"found {current.version}"
            )

        if entity.tenant_id != tenant_id:
            raise TenantIsolationError(
                "entity tenant cannot be changed"
            )

        if entity.entity_id != current.entity_id:
            raise DataIntegrityError(
                "entity id cannot be changed"
            )

        updated = replace(
            entity,
            version=current.version + 1,
            created_at=current.created_at,
            updated_at=utc_now(),
        )

        self._entities[updated.entity_id] = updated

        self.append_event(
            tenant_id=tenant_id,
            aggregate_type=type(updated).__name__,
            aggregate_id=updated.entity_id,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
            correlation_id=correlation_id,
        )

        return updated

    def list_type(
        self,
        *,
        tenant_id: str,
        entity_type: type[T],
    ) -> tuple[T, ...]:
        return tuple(
            entity
            for entity in self._entities.values()
            if (
                entity.tenant_id == tenant_id
                and isinstance(entity, entity_type)
            )
        )  # type: ignore[return-value]

    def append_event(
        self,
        *,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        actor_id: str,
        payload: dict | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> SpineEvent:
        key = (aggregate_type, aggregate_id)

        sequence = self._aggregate_sequence.get(key, 0) + 1

        event = make_event(
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            sequence=sequence,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

        self._events.append(event)
        self._aggregate_sequence[key] = sequence

        return event

    def events_for(
        self,
        *,
        tenant_id: str,
        aggregate_id: str,
    ) -> tuple[SpineEvent, ...]:
        return tuple(
            event
            for event in self._events
            if (
                event.tenant_id == tenant_id
                and event.aggregate_id == aggregate_id
            )
        )

    def all_events(
        self,
        *,
        tenant_id: str,
    ) -> tuple[SpineEvent, ...]:
        return tuple(
            event
            for event in self._events
            if event.tenant_id == tenant_id
        )
