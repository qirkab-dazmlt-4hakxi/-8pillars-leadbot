from __future__ import annotations


ENTRY_ENTITY = (
    "goat.finance.journal_entry"
)

BANK_TRANSACTION_ENTITY = (
    "goat.finance.bank_transaction"
)

BOOKKEEPING_DECISION_ENTITY = (
    "goat.finance.bookkeeping_decision"
)


class FinancialRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id: str,
        actor_id: str = (
            "goat-financial-intelligence"
        ),
    ) -> None:
        self.store = store
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def _upsert(
        self,
        *,
        entity_type: str,
        entity_id: str,
        payload: dict,
    ):
        current = self.store.get_entity(
            tenant_id=(
                self.tenant_id
            ),
            entity_type=(
                entity_type
            ),
            entity_id=(
                entity_id
            ),
        )

        expected = (
            None
            if current is None
            else int(
                current.version
            )
        )

        return self.store.put_entity(
            tenant_id=(
                self.tenant_id
            ),
            entity_type=(
                entity_type
            ),
            entity_id=(
                entity_id
            ),
            payload=payload,
            actor_id=(
                self.actor_id
            ),
            expected_version=(
                expected
            ),
        )

    def save_entry(
        self,
        entry,
    ) -> None:
        self._upsert(
            entity_type=(
                ENTRY_ENTITY
            ),
            entity_id=(
                entry.entry_id
            ),
            payload={
                "entry_id":
                    entry.entry_id,
                "entity_id":
                    entry.entity_id,
                "entry_date":
                    entry.entry_date.isoformat(),
                "source_type":
                    entry.source_type,
                "source_id":
                    entry.source_id,
                "memo":
                    entry.memo,
                "lines": [
                    {
                        "account_code":
                            line.account_code,
                        "debit":
                            str(
                                line.debit
                            ),
                        "credit":
                            str(
                                line.credit
                            ),
                        "project_id":
                            line.project_id,
                        "cost_code":
                            line.cost_code,
                        "vendor_id":
                            line.vendor_id,
                        "tax_code":
                            line.tax_code,
                        "memo":
                            line.memo,
                    }
                    for line
                    in entry.lines
                ],
            },
        )

    def save_bank_transaction(
        self,
        transaction,
    ) -> None:
        self._upsert(
            entity_type=(
                BANK_TRANSACTION_ENTITY
            ),
            entity_id=(
                transaction.transaction_id
            ),
            payload={
                "transaction_id":
                    transaction.transaction_id,
                "entity_id":
                    transaction.entity_id,
                "provider":
                    transaction.provider,
                "account_id":
                    transaction.account_id,
                "posted_date":
                    transaction.posted_date.isoformat(),
                "amount":
                    str(
                        transaction.amount
                    ),
                "direction":
                    transaction.direction.value,
                "description":
                    transaction.description,
                "merchant_name":
                    transaction.merchant_name,
                "pending":
                    transaction.pending,
                "external_hash":
                    transaction.external_hash,
                "metadata":
                    dict(
                        transaction.metadata
                    ),
            },
        )

    def save_bookkeeping_decision(
        self,
        decision,
    ) -> None:
        self._upsert(
            entity_type=(
                BOOKKEEPING_DECISION_ENTITY
            ),
            entity_id=(
                decision.transaction_id
            ),
            payload={
                "transaction_id":
                    decision.transaction_id,
                "status":
                    decision.status.value,
                "journal_entry_id":
                    decision.journal_entry_id,
                "classification_kind":
                    decision.classification.kind.value,
                "classification_confidence":
                    decision.classification.confidence,
                "tax_code":
                    decision.tax_assessment.tax_code,
                "reason":
                    decision.reason,
            },
        )
