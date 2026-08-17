from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from leadbot_v2.goat.financial_intelligence import (
    CashEvent,
)

from leadbot_v2.goat.financial_intelligence.canonical import (
    money,
)

from .models import (
    AgingSummary,
    OpenItemStatus,
    Payable,
    Receivable,
)


ZERO = Decimal(
    "0.00"
)


def _aging_bucket(
    *,
    due_date,
    as_of,
):
    days = (
        as_of
        - due_date
    ).days

    if days <= 0:
        return "current"

    if days <= 30:
        return "days_1_30"

    if days <= 60:
        return "days_31_60"

    if days <= 90:
        return "days_61_90"

    return "days_90_plus"


class ReceivablesLedger:
    def __init__(
        self,
        *,
        entity_id: str,
    ) -> None:
        self.entity_id = (
            entity_id
        )

        self._items = {}

    def add(
        self,
        item: Receivable,
    ) -> None:
        if (
            item.entity_id
            != self.entity_id
        ):
            raise ValueError(
                "cross-entity receivable forbidden"
            )

        if (
            item.receivable_id
            in self._items
        ):
            raise ValueError(
                "duplicate receivable"
            )

        if (
            money(
                item.outstanding_amount
            )
            > money(
                item.original_amount
            )
        ):
            raise ValueError(
                "outstanding amount exceeds original amount"
            )

        self._items[
            item.receivable_id
        ] = item

    def apply_collection(
        self,
        receivable_id: str,
        amount,
    ) -> Receivable:
        item = self._items[
            receivable_id
        ]

        amount = money(
            amount
        )

        if amount <= ZERO:
            raise ValueError(
                "collection must be positive"
            )

        outstanding = money(
            item.outstanding_amount
            - amount
        )

        if outstanding < ZERO:
            raise ValueError(
                "collection exceeds outstanding balance"
            )

        status = (
            OpenItemStatus.SETTLED
            if outstanding == ZERO
            else OpenItemStatus.PARTIAL
        )

        updated = replace(
            item,
            outstanding_amount=(
                outstanding
            ),
            status=status,
        )

        self._items[
            receivable_id
        ] = updated

        return updated

    def open_items(
        self,
    ):
        return tuple(
            item
            for item
            in self._items.values()
            if item.status
            in {
                OpenItemStatus.OPEN,
                OpenItemStatus.PARTIAL,
                OpenItemStatus.DISPUTED,
            }
        )

    def aging(
        self,
        *,
        as_of: date,
    ) -> AgingSummary:
        buckets = {
            "current":
                ZERO,
            "days_1_30":
                ZERO,
            "days_31_60":
                ZERO,
            "days_61_90":
                ZERO,
            "days_90_plus":
                ZERO,
        }

        for item in (
            self.open_items()
        ):
            bucket = _aging_bucket(
                due_date=(
                    item.due_date
                ),
                as_of=as_of,
            )

            buckets[
                bucket
            ] += money(
                item.outstanding_amount
            )

        for key in buckets:
            buckets[
                key
            ] = money(
                buckets[
                    key
                ]
            )

        total = money(
            sum(
                buckets.values(),
                ZERO,
            )
        )

        return AgingSummary(
            total=total,
            **buckets,
        )

    def expected_cash_events(
        self,
    ):
        return tuple(
            CashEvent(
                event_date=(
                    item.due_date
                ),
                amount=(
                    money(
                        item.outstanding_amount
                    )
                ),
                label=(
                    f"AR:{item.receivable_id}"
                ),
                confidence=max(
                    0.0,
                    min(
                        1.0,
                        item.collection_probability,
                    ),
                ),
                project_id=(
                    item.project_id
                ),
            )
            for item
            in self.open_items()
        )


class PayablesLedger:
    def __init__(
        self,
        *,
        entity_id: str,
    ) -> None:
        self.entity_id = (
            entity_id
        )

        self._items = {}

    def add(
        self,
        item: Payable,
    ) -> None:
        if (
            item.entity_id
            != self.entity_id
        ):
            raise ValueError(
                "cross-entity payable forbidden"
            )

        if (
            item.payable_id
            in self._items
        ):
            raise ValueError(
                "duplicate payable"
            )

        if (
            money(
                item.outstanding_amount
            )
            > money(
                item.original_amount
            )
        ):
            raise ValueError(
                "outstanding amount exceeds original amount"
            )

        self._items[
            item.payable_id
        ] = item

    def apply_payment(
        self,
        payable_id: str,
        amount,
    ) -> Payable:
        item = self._items[
            payable_id
        ]

        amount = money(
            amount
        )

        if amount <= ZERO:
            raise ValueError(
                "payment must be positive"
            )

        outstanding = money(
            item.outstanding_amount
            - amount
        )

        if outstanding < ZERO:
            raise ValueError(
                "payment exceeds outstanding balance"
            )

        status = (
            OpenItemStatus.SETTLED
            if outstanding == ZERO
            else OpenItemStatus.PARTIAL
        )

        updated = replace(
            item,
            outstanding_amount=(
                outstanding
            ),
            status=status,
        )

        self._items[
            payable_id
        ] = updated

        return updated

    def open_items(
        self,
    ):
        return tuple(
            item
            for item
            in self._items.values()
            if item.status
            in {
                OpenItemStatus.OPEN,
                OpenItemStatus.PARTIAL,
                OpenItemStatus.DISPUTED,
            }
        )

    def aging(
        self,
        *,
        as_of: date,
    ) -> AgingSummary:
        buckets = {
            "current":
                ZERO,
            "days_1_30":
                ZERO,
            "days_31_60":
                ZERO,
            "days_61_90":
                ZERO,
            "days_90_plus":
                ZERO,
        }

        for item in (
            self.open_items()
        ):
            bucket = _aging_bucket(
                due_date=(
                    item.due_date
                ),
                as_of=as_of,
            )

            buckets[
                bucket
            ] += money(
                item.outstanding_amount
            )

        for key in buckets:
            buckets[
                key
            ] = money(
                buckets[
                    key
                ]
            )

        total = money(
            sum(
                buckets.values(),
                ZERO,
            )
        )

        return AgingSummary(
            total=total,
            **buckets,
        )

    def expected_cash_events(
        self,
    ):
        return tuple(
            CashEvent(
                event_date=(
                    item.due_date
                ),
                amount=-money(
                    item.outstanding_amount
                ),
                label=(
                    f"AP:{item.payable_id}"
                ),
                confidence=1.0,
                project_id=(
                    item.project_id
                ),
            )
            for item
            in self.open_items()
        )
