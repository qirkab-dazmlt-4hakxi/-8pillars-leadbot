from __future__ import annotations

from .ap_ar import (
    PayablesLedger,
    ReceivablesLedger,
)

from .close import (
    MonthEndCloseEngine,
)

from .collections import (
    CollectionsPrioritizer,
)

from .costcoding import (
    AdaptiveCostCoder,
)

from .documents import (
    DocumentMatcher,
)

from .providers import (
    ProviderControlPlane,
)

from .surveillance import (
    ProfitabilitySurveillance,
)

from .sync import (
    BankSynchronizationEngine,
    SyncStateStore,
)


class FinancialOperationsService:
    def __init__(
        self,
        *,
        entity_id: str,
        financial_system,
        secret_resolver,
        repository=None,
    ) -> None:
        if (
            financial_system.entity_id
            != entity_id
        ):
            raise ValueError(
                "financial system entity mismatch"
            )

        self.entity_id = (
            entity_id
        )

        self.financial_system = (
            financial_system
        )

        self.repository = (
            repository
        )

        self.providers = (
            ProviderControlPlane(
                secret_resolver=(
                    secret_resolver
                )
            )
        )

        self.sync_state = (
            SyncStateStore()
        )

        self.sync_engine = (
            BankSynchronizationEngine(
                control_plane=(
                    self.providers
                ),
                state_store=(
                    self.sync_state
                ),
            )
        )

        self.receivables = (
            ReceivablesLedger(
                entity_id=(
                    entity_id
                )
            )
        )

        self.payables = (
            PayablesLedger(
                entity_id=(
                    entity_id
                )
            )
        )

        self.documents = (
            DocumentMatcher()
        )

        self.cost_coder = (
            AdaptiveCostCoder()
        )

        self.collections = (
            CollectionsPrioritizer()
        )

        self.close_engine = (
            MonthEndCloseEngine()
        )

        self.profitability = (
            ProfitabilitySurveillance()
        )

    def sync_provider(
        self,
        *,
        provider_name,
        start_date,
        end_date,
    ):
        result = self.sync_engine.sync(
            provider_name=(
                provider_name
            ),
            entity_id=(
                self.entity_id
            ),
            start_date=(
                start_date
            ),
            end_date=(
                end_date
            ),
            financial_system=(
                self.financial_system
            ),
        )

        if self.repository:
            for cursor in (
                result.next_cursors
            ):
                self.repository.save_cursor(
                    cursor
                )

            for correction in (
                result.corrections
            ):
                self.repository.save_correction(
                    correction
                )

        return result

    def close_period(
        self,
        *,
        period_end,
        reconciliation_report,
        anomalies=(),
    ):
        report = (
            self.close_engine.evaluate(
                entity_id=(
                    self.entity_id
                ),
                period_end=(
                    period_end
                ),
                financial_system=(
                    self.financial_system
                ),
                reconciliation_report=(
                    reconciliation_report
                ),
                anomalies=(
                    anomalies
                ),
                receivables_aging=(
                    self.receivables
                    .aging(
                        as_of=(
                            period_end
                        )
                    )
                ),
                payables_aging=(
                    self.payables
                    .aging(
                        as_of=(
                            period_end
                        )
                    )
                ),
            )
        )

        if self.repository:
            self.repository.save_close_report(
                report
            )

        return report
