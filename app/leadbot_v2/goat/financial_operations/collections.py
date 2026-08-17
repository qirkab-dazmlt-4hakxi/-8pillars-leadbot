from __future__ import annotations

from datetime import date

from .models import (
    CollectionCandidate,
)


class CollectionsPrioritizer:
    def rank(
        self,
        receivables,
        *,
        as_of: date,
    ):
        candidates = []

        for item in receivables:
            days_past_due = max(
                0,
                (
                    as_of
                    - item.due_date
                ).days,
            )

            probability = max(
                0.0,
                min(
                    1.0,
                    item.collection_probability,
                ),
            )

            amount = float(
                item.outstanding_amount
            )

            aging_multiplier = (
                1.0
                + min(
                    4.0,
                    days_past_due
                    / 30.0,
                )
            )

            uncertainty_multiplier = (
                1.0
                + (
                    1.0
                    - probability
                )
            )

            priority = (
                amount
                * aging_multiplier
                * uncertainty_multiplier
            )

            candidates.append(
                CollectionCandidate(
                    receivable_id=(
                        item.receivable_id
                    ),
                    customer_id=(
                        item.customer_id
                    ),
                    outstanding_amount=(
                        item.outstanding_amount
                    ),
                    days_past_due=(
                        days_past_due
                    ),
                    collection_probability=(
                        probability
                    ),
                    priority_score=(
                        priority
                    ),
                )
            )

        candidates.sort(
            key=lambda item: (
                item.priority_score,
                item.receivable_id,
            ),
            reverse=True,
        )

        return tuple(
            candidates
        )
