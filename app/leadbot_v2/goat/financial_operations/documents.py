from __future__ import annotations

import re

from datetime import date

from leadbot_v2.goat.financial_intelligence.canonical import (
    money,
)

from .models import (
    DocumentMatch,
)


TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+"
)


def tokens(
    value: str | None,
):
    if not value:
        return frozenset()

    return frozenset(
        token.lower()
        for token
        in TOKEN_RE.findall(
            value
        )
        if len(
            token
        ) >= 2
    )


def similarity(
    left: str | None,
    right: str | None,
) -> float:
    a = tokens(
        left
    )
    b = tokens(
        right
    )

    if not a or not b:
        return 0.0

    return (
        len(
            a & b
        )
        / len(
            a | b
        )
    )


class DocumentMatcher:
    def match_invoice(
        self,
        invoice,
        transactions,
        *,
        vendor_display_name: str | None = None,
    ):
        ranked = []

        for transaction in transactions:
            if (
                transaction.entity_id
                != invoice.entity_id
            ):
                continue

            amount_score = (
                1.0
                if money(
                    transaction.amount
                )
                == money(
                    invoice.amount
                )
                else max(
                    0.0,
                    1.0
                    - (
                        abs(
                            float(
                                transaction.amount
                                - invoice.amount
                            )
                        )
                        / max(
                            1.0,
                            float(
                                invoice.amount
                            ),
                        )
                    ),
                )
            )

            date_distance = abs(
                (
                    transaction.posted_date
                    - invoice.invoice_date
                ).days
            )

            date_score = max(
                0.0,
                1.0
                - date_distance
                / 30.0,
            )

            counterparty_score = similarity(
                vendor_display_name
                or invoice.vendor_id,
                transaction.merchant_name
                or transaction.description,
            )

            transaction_project = (
                transaction.metadata.get(
                    "project_id"
                )
            )

            project_score = (
                1.0
                if (
                    invoice.project_id
                    and transaction_project
                    == invoice.project_id
                )
                else 0.0
            )

            confidence = min(
                1.0,
                amount_score
                * 0.50
                + date_score
                * 0.20
                + counterparty_score
                * 0.25
                + project_score
                * 0.05,
            )

            ranked.append(
                DocumentMatch(
                    document_id=(
                        invoice.invoice_id
                    ),
                    transaction_id=(
                        transaction
                        .transaction_id
                    ),
                    confidence=(
                        confidence
                    ),
                    amount_score=(
                        amount_score
                    ),
                    date_score=(
                        date_score
                    ),
                    counterparty_score=(
                        counterparty_score
                    ),
                    project_score=(
                        project_score
                    ),
                    reason=(
                        "deterministic amount/date/"
                        "counterparty/project matching"
                    ),
                )
            )

        ranked.sort(
            key=lambda match: (
                match.confidence,
                match.transaction_id,
            ),
            reverse=True,
        )

        return tuple(
            ranked
        )

    def match_receipt(
        self,
        receipt,
        transactions,
    ):
        pseudo_invoice = type(
            "_ReceiptInvoice",
            (),
            {
                "invoice_id":
                    receipt.receipt_id,
                "entity_id":
                    receipt.entity_id,
                "vendor_id":
                    receipt.merchant_name,
                "invoice_date":
                    receipt.receipt_date,
                "amount":
                    receipt.amount,
                "project_id":
                    receipt.project_id,
            },
        )()

        return self.match_invoice(
            pseudo_invoice,
            transactions,
            vendor_display_name=(
                receipt.merchant_name
            ),
        )
