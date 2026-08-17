from __future__ import annotations

from dataclasses import dataclass

from .models import (
    BankDirection,
    BankTransaction,
    Classification,
    EntityIsolationError,
    JournalLine,
    PostingStatus,
    TransactionKind,
)


@dataclass(frozen=True)
class BookkeepingDecision:
    transaction_id: str

    status: PostingStatus

    journal_entry_id: str | None

    classification: Classification

    tax_assessment: object

    reason: str


class AutoBookkeeper:
    def __init__(
        self,
        ledger,
        *,
        auto_post_threshold: float = 0.90,
    ) -> None:
        self.ledger = ledger

        if not (
            0.0
            <= auto_post_threshold
            <= 1.0
        ):
            raise ValueError(
                "auto_post_threshold must be in [0,1]"
            )

        self.auto_post_threshold = float(
            auto_post_threshold
        )

    def process(
        self,
        transaction: BankTransaction,
        classification: Classification,
        tax_assessment,
        *,
        bank_account_code: str,
    ) -> BookkeepingDecision:
        if (
            transaction.entity_id
            != self.ledger.entity_id
        ):
            raise EntityIsolationError(
                "bank transaction entity does not match ledger"
            )

        if transaction.pending:
            return self._review(
                transaction,
                classification,
                tax_assessment,
                "pending bank transaction",
            )

        if (
            classification.review_required
            or tax_assessment.requires_review
        ):
            return self._review(
                transaction,
                classification,
                tax_assessment,
                "classification or tax review required",
            )

        if (
            classification.confidence
            < self.auto_post_threshold
        ):
            return self._review(
                transaction,
                classification,
                tax_assessment,
                "classification confidence below "
                "automatic posting threshold",
            )

        counter = (
            classification
            .counter_account_code
        )

        if not counter:
            return self._review(
                transaction,
                classification,
                tax_assessment,
                "counter account missing",
            )

        kind = (
            classification.kind
        )

        amount = (
            transaction.amount
        )

        common = {
            "project_id":
                classification.project_id,
            "cost_code":
                classification.cost_code,
            "vendor_id":
                classification.vendor_id,
            "tax_code":
                tax_assessment.tax_code,
        }

        if kind in {
            TransactionKind.EXPENSE,
            TransactionKind.REVENUE,
            TransactionKind.TRANSFER,
            TransactionKind.CREDIT_CARD_PAYMENT,
        }:
            if (
                transaction.direction
                is BankDirection.OUTFLOW
            ):
                lines = (
                    JournalLine(
                        account_code=counter,
                        debit=amount,
                        memo=(
                            transaction.description
                        ),
                        **common,
                    ),
                    JournalLine(
                        account_code=(
                            bank_account_code
                        ),
                        credit=amount,
                        memo=(
                            transaction.description
                        ),
                        **common,
                    ),
                )

            else:
                lines = (
                    JournalLine(
                        account_code=(
                            bank_account_code
                        ),
                        debit=amount,
                        memo=(
                            transaction.description
                        ),
                        **common,
                    ),
                    JournalLine(
                        account_code=counter,
                        credit=amount,
                        memo=(
                            transaction.description
                        ),
                        **common,
                    ),
                )

        elif kind is (
            TransactionKind.OWNER_DRAW
        ):
            if (
                transaction.direction
                is not BankDirection.OUTFLOW
            ):
                return self._review(
                    transaction,
                    classification,
                    tax_assessment,
                    "owner draw expected to be outflow",
                )

            lines = (
                JournalLine(
                    account_code=counter,
                    debit=amount,
                    memo=(
                        transaction.description
                    ),
                    **common,
                ),
                JournalLine(
                    account_code=(
                        bank_account_code
                    ),
                    credit=amount,
                    memo=(
                        transaction.description
                    ),
                    **common,
                ),
            )

        elif kind is (
            TransactionKind
            .CAPITAL_CONTRIBUTION
        ):
            if (
                transaction.direction
                is not BankDirection.INFLOW
            ):
                return self._review(
                    transaction,
                    classification,
                    tax_assessment,
                    "capital contribution expected to be inflow",
                )

            lines = (
                JournalLine(
                    account_code=(
                        bank_account_code
                    ),
                    debit=amount,
                    memo=(
                        transaction.description
                    ),
                    **common,
                ),
                JournalLine(
                    account_code=counter,
                    credit=amount,
                    memo=(
                        transaction.description
                    ),
                    **common,
                ),
            )

        else:
            return self._review(
                transaction,
                classification,
                tax_assessment,
                "transaction type is not approved "
                "for autonomous posting",
            )

        entry = (
            self.ledger.create_entry(
                entity_id=(
                    transaction.entity_id
                ),
                entry_date=(
                    transaction.posted_date
                ),
                source_type=(
                    "bank_transaction"
                ),
                source_id=(
                    transaction.transaction_id
                ),
                memo=(
                    transaction.description
                ),
                lines=lines,
            )
        )

        posted = self.ledger.post(
            entry
        )

        return BookkeepingDecision(
            transaction_id=(
                transaction.transaction_id
            ),
            status=(
                PostingStatus.AUTO_POSTED
            ),
            journal_entry_id=(
                posted.entry_id
            ),
            classification=(
                classification
            ),
            tax_assessment=(
                tax_assessment
            ),
            reason=(
                "high-confidence autonomous "
                "double-entry posting"
            ),
        )

    @staticmethod
    def _review(
        transaction,
        classification,
        tax_assessment,
        reason,
    ):
        return BookkeepingDecision(
            transaction_id=(
                transaction.transaction_id
            ),
            status=(
                PostingStatus.REVIEW_REQUIRED
            ),
            journal_entry_id=None,
            classification=classification,
            tax_assessment=(
                tax_assessment
            ),
            reason=reason,
        )
