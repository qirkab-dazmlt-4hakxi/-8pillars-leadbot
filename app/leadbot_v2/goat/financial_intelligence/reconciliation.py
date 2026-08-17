from __future__ import annotations

from dataclasses import dataclass

from .canonical import (
    money,
)


@dataclass(frozen=True)
class ReconciliationMatch:
    transaction_id: str

    journal_entry_id: str

    match_type: str

    confidence: float


@dataclass(frozen=True)
class ReconciliationReport:
    matched: tuple[
        ReconciliationMatch,
        ...,
    ]

    unmatched_transaction_ids: tuple[
        str,
        ...,
    ]

    unmatched_journal_entry_ids: tuple[
        str,
        ...,
    ]

    reconciled: bool


class ReconciliationEngine:
    def reconcile(
        self,
        *,
        transactions,
        ledger,
        bank_account_code: str,
        date_tolerance_days: int = 3,
    ) -> ReconciliationReport:
        transactions = tuple(
            transactions
        )

        for transaction in transactions:
            if (
                transaction.entity_id
                != ledger.entity_id
            ):
                raise ValueError(
                    "cross-entity reconciliation forbidden"
                )

        postings = list(
            ledger.bank_postings(
                bank_account_code
            )
        )

        used_postings = set()

        matches = []
        unmatched_transactions = []

        for transaction in transactions:
            signed = money(
                transaction.signed_amount
            )

            exact_source = [
                posting
                for posting
                in postings
                if (
                    posting[
                        "source_id"
                    ]
                    == transaction.transaction_id
                    and money(
                        posting[
                            "signed_amount"
                        ]
                    )
                    == signed
                )
            ]

            chosen = None
            match_type = None
            confidence = 0.0

            for posting in exact_source:
                if (
                    posting[
                        "entry_id"
                    ]
                    not in used_postings
                ):
                    chosen = posting
                    match_type = (
                        "source-id"
                    )
                    confidence = 1.0
                    break

            if chosen is None:
                candidates = []

                for posting in postings:
                    if (
                        posting[
                            "entry_id"
                        ]
                        in used_postings
                    ):
                        continue

                    if (
                        money(
                            posting[
                                "signed_amount"
                            ]
                        )
                        != signed
                    ):
                        continue

                    delta = abs(
                        (
                            posting[
                                "entry_date"
                            ]
                            - transaction.posted_date
                        ).days
                    )

                    if (
                        delta
                        <= date_tolerance_days
                    ):
                        candidates.append(
                            (
                                delta,
                                posting[
                                    "entry_id"
                                ],
                                posting,
                            )
                        )

                if candidates:
                    candidates.sort(
                        key=lambda row: (
                            row[0],
                            row[1],
                        )
                    )

                    chosen = (
                        candidates[
                            0
                        ][
                            2
                        ]
                    )

                    match_type = (
                        "amount-date"
                    )

                    confidence = max(
                        0.70,
                        0.95
                        - candidates[
                            0
                        ][
                            0
                        ]
                        * 0.05,
                    )

            if chosen is None:
                unmatched_transactions.append(
                    transaction.transaction_id
                )
                continue

            used_postings.add(
                chosen[
                    "entry_id"
                ]
            )

            matches.append(
                ReconciliationMatch(
                    transaction_id=(
                        transaction.transaction_id
                    ),
                    journal_entry_id=(
                        chosen[
                            "entry_id"
                        ]
                    ),
                    match_type=(
                        match_type
                    ),
                    confidence=(
                        confidence
                    ),
                )
            )

        unmatched_journal = tuple(
            posting[
                "entry_id"
            ]
            for posting
            in postings
            if posting[
                "entry_id"
            ]
            not in used_postings
        )

        return ReconciliationReport(
            matched=tuple(
                matches
            ),
            unmatched_transaction_ids=(
                tuple(
                    unmatched_transactions
                )
            ),
            unmatched_journal_entry_ids=(
                unmatched_journal
            ),
            reconciled=(
                not unmatched_transactions
                and not unmatched_journal
            ),
        )
