from __future__ import annotations

from .anomaly import (
    FinancialAnomalyDetector,
)

from .banking import (
    BankFeedIngestor,
)

from .bookkeeper import (
    AutoBookkeeper,
)

from .capital import (
    CapitalAllocator,
)

from .cashflow import (
    CashFlowForecaster,
)

from .chart import (
    default_construction_chart,
)

from .classifier import (
    TransactionClassifier,
)

from .compliance import (
    ComplianceCalendar,
)

from .jobcost import (
    JobCostAnalyzer,
)

from .ledger import (
    GeneralLedger,
)

from .models import (
    EntityIsolationError,
)

from .reconciliation import (
    ReconciliationEngine,
)

from .tax import (
    default_tax_engine,
)


class FinancialIntelligenceSystem:
    def __init__(
        self,
        *,
        entity_id: str,
        repository=None,
        auto_post_threshold: float = 0.90,
    ) -> None:
        if not entity_id.strip():
            raise ValueError(
                "entity_id required"
            )

        self.entity_id = entity_id
        self.repository = repository

        self.chart = (
            default_construction_chart()
        )

        self.ledger = (
            GeneralLedger(
                self.chart,
                entity_id=(
                    entity_id
                ),
            )
        )

        self.bank_ingestor = (
            BankFeedIngestor()
        )

        self.classifier = (
            TransactionClassifier()
        )

        self.tax = (
            default_tax_engine()
        )

        self.bookkeeper = (
            AutoBookkeeper(
                self.ledger,
                auto_post_threshold=(
                    auto_post_threshold
                ),
            )
        )

        self.reconciliation = (
            ReconciliationEngine()
        )

        self.jobcost = (
            JobCostAnalyzer()
        )

        self.cashflow = (
            CashFlowForecaster()
        )

        self.anomalies = (
            FinancialAnomalyDetector()
        )

        self.capital = (
            CapitalAllocator()
        )

        self.compliance = (
            ComplianceCalendar()
        )

        self.review_queue = []

        self.transactions = {}

    def add_classification_rule(
        self,
        rule,
    ) -> None:
        self.classifier.add_rule(
            rule
        )

    def ingest_raw_transactions(
        self,
        rows,
    ):
        rows = tuple(
            rows
        )

        for row in rows:
            if (
                row.entity_id
                != self.entity_id
            ):
                raise EntityIsolationError(
                    "cross-entity bank transaction ingestion forbidden"
                )

        accepted, duplicates = (
            self.bank_ingestor.ingest(
                rows
            )
        )

        for transaction in accepted:
            self.transactions[
                transaction.transaction_id
            ] = transaction

            if self.repository:
                self.repository.save_bank_transaction(
                    transaction
                )

        return (
            accepted,
            duplicates,
        )

    def process_transaction(
        self,
        transaction,
        *,
        bank_account_code: str,
        project_id=None,
        cost_code=None,
        vendor_id=None,
    ):
        if (
            transaction.entity_id
            != self.entity_id
        ):
            raise EntityIsolationError(
                "cross-entity transaction processing forbidden"
            )

        classification = (
            self.classifier.classify(
                transaction,
                project_id=(
                    project_id
                ),
                cost_code=(
                    cost_code
                ),
                vendor_id=(
                    vendor_id
                ),
            )
        )

        assessment = (
            self.tax.assess(
                classification,
                on_date=(
                    transaction.posted_date
                ),
            )
        )

        decision = (
            self.bookkeeper.process(
                transaction,
                classification,
                assessment,
                bank_account_code=(
                    bank_account_code
                ),
            )
        )

        if (
            decision.journal_entry_id
        ):
            entry = next(
                entry
                for entry
                in self.ledger.entries()
                if (
                    entry.entry_id
                    == decision.journal_entry_id
                )
            )

            if self.repository:
                self.repository.save_entry(
                    entry
                )

        else:
            self.review_queue.append(
                decision
            )

        if self.repository:
            self.repository.save_bookkeeping_decision(
                decision
            )

        return decision
