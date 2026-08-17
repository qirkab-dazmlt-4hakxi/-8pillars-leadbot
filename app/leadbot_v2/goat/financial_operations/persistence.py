from __future__ import annotations

from leadbot_v2.goat.financial_intelligence.canonical import (
    stable_hash,
)


SYNC_CURSOR_ENTITY = (
    "goat.finance_ops.sync_cursor"
)

SYNC_CORRECTION_ENTITY = (
    "goat.finance_ops.sync_correction"
)

CLOSE_REPORT_ENTITY = (
    "goat.finance_ops.close_report"
)


class FinancialOperationsRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id: str,
        actor_id: str = (
            "goat-financial-operations"
        ),
    ) -> None:
        self.store = store

        self.tenant_id = (
            tenant_id
        )

        self.actor_id = (
            actor_id
        )

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

    def save_cursor(
        self,
        cursor,
    ) -> None:
        entity_id = stable_hash(
            {
                "provider":
                    cursor.provider_name,
                "entity":
                    cursor.entity_id,
                "account":
                    cursor.external_account_id,
            }
        )[:32]

        self._upsert(
            entity_type=(
                SYNC_CURSOR_ENTITY
            ),
            entity_id=(
                entity_id
            ),
            payload={
                "provider_name":
                    cursor.provider_name,
                "entity_id":
                    cursor.entity_id,
                "external_account_id":
                    cursor.external_account_id,
                "cursor":
                    cursor.cursor,
                "updated_at":
                    cursor.updated_at
                    .isoformat(),
            },
        )

    def save_correction(
        self,
        correction,
    ) -> None:
        entity_id = stable_hash(
            {
                "provider":
                    correction.provider_name,
                "entity":
                    correction.entity_id,
                "account":
                    correction.external_account_id,
                "transaction":
                    correction.external_transaction_id,
                "new":
                    correction.new_fingerprint,
            }
        )[:32]

        self._upsert(
            entity_type=(
                SYNC_CORRECTION_ENTITY
            ),
            entity_id=(
                entity_id
            ),
            payload={
                "provider_name":
                    correction.provider_name,
                "entity_id":
                    correction.entity_id,
                "external_account_id":
                    correction.external_account_id,
                "external_transaction_id":
                    correction.external_transaction_id,
                "previous_fingerprint":
                    correction.previous_fingerprint,
                "new_fingerprint":
                    correction.new_fingerprint,
                "reason":
                    correction.reason,
            },
        )

    def save_close_report(
        self,
        report,
    ) -> None:
        entity_id = stable_hash(
            {
                "entity":
                    report.entity_id,
                "period_end":
                    report.period_end,
            }
        )[:32]

        self._upsert(
            entity_type=(
                CLOSE_REPORT_ENTITY
            ),
            entity_id=(
                entity_id
            ),
            payload={
                "entity_id":
                    report.entity_id,
                "period_end":
                    report.period_end
                    .isoformat(),
                "closable":
                    report.closable,
                "findings": [
                    {
                        "finding_id":
                            finding.finding_id,
                        "severity":
                            finding.severity.value,
                        "message":
                            finding.message,
                    }
                    for finding
                    in report.findings
                ],
            },
        )
