from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class ComplianceStatus(str, Enum):
    OPEN = "open"
    PREPARED = "prepared"
    FILED = "filed"
    PAID = "paid"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ComplianceObligation:
    obligation_id: str

    entity_id: str

    name: str

    authority: str

    due_date: date

    rule_version: str

    source_reference: str

    status: ComplianceStatus = (
        ComplianceStatus.OPEN
    )

    notes: str = ""


class ComplianceCalendar:
    def __init__(
        self,
    ) -> None:
        self._items: dict[
            str,
            ComplianceObligation,
        ] = {}

    def add(
        self,
        obligation: ComplianceObligation,
    ) -> None:
        if (
            obligation.obligation_id
            in self._items
        ):
            raise ValueError(
                "duplicate compliance obligation"
            )

        self._items[
            obligation.obligation_id
        ] = obligation

    def upcoming(
        self,
        *,
        as_of: date,
        days: int = 90,
        entity_id: str | None = None,
    ):
        cutoff = (
            as_of
            + timedelta(
                days=days
            )
        )

        return tuple(
            sorted(
                (
                    item
                    for item
                    in self._items.values()
                    if (
                        item.status
                        is ComplianceStatus.OPEN
                        and (
                            entity_id is None
                            or item.entity_id
                            == entity_id
                        )
                        and as_of
                        <= item.due_date
                        <= cutoff
                    )
                ),
                key=lambda item: (
                    item.due_date,
                    item.obligation_id,
                ),
            )
        )

    def overdue(
        self,
        *,
        as_of: date,
        entity_id: str | None = None,
    ):
        return tuple(
            sorted(
                (
                    item
                    for item
                    in self._items.values()
                    if (
                        item.status
                        is ComplianceStatus.OPEN
                        and (
                            entity_id is None
                            or item.entity_id
                            == entity_id
                        )
                        and item.due_date
                        < as_of
                    )
                ),
                key=lambda item: (
                    item.due_date,
                    item.obligation_id,
                ),
            )
        )
