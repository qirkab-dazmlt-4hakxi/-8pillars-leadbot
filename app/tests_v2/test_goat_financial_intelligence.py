from __future__ import annotations

import unittest

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from leadbot_v2.goat.financial_intelligence import (
    AccountingInvariantError,
    BankDirection,
    CapitalAllocator,
    CapitalOption,
    CashEvent,
    CashFlowForecaster,
    CashRisk,
    ClassificationRule,
    ComplianceCalendar,
    ComplianceObligation,
    EntityIsolationError,
    FinancialAnomalyDetector,
    FinancialIntelligenceSystem,
    FinancialRepository,
    GeneralLedger,
    JobCostAnalyzer,
    JobFinancialState,
    JournalLine,
    PostingStatus,
    RawBankTransaction,
    ReconciliationEngine,
    TransactionKind,
    default_construction_chart,
    install_financial_experts,
    money,
)

from leadbot_v2.goat.superintelligence import (
    AutonomyLevel,
    CognitiveKernel,
)


DAY = date(
    2026,
    8,
    17,
)

ENTITY = "twins-development"


class FakeStore:
    def __init__(
        self,
    ):
        self.entities = {}

    def get_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        include_deleted=False,
    ):
        return deepcopy(
            self.entities.get(
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                )
            )
        )

    def put_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        payload,
        actor_id,
        expected_version=None,
    ):
        key = (
            tenant_id,
            entity_type,
            entity_id,
        )

        current = (
            self.entities.get(
                key
            )
        )

        if current is None:
            if (
                expected_version
                is not None
            ):
                raise RuntimeError(
                    "version conflict"
                )

            version = 1

        else:
            if (
                current.version
                != expected_version
            ):
                raise RuntimeError(
                    "version conflict"
                )

            version = (
                current.version
                + 1
            )

        record = SimpleNamespace(
            version=version,
            payload=deepcopy(
                payload
            ),
        )

        self.entities[
            key
        ] = record

        return deepcopy(
            record
        )


class LedgerTests(
    unittest.TestCase
):
    def ledger(
        self,
    ):
        return GeneralLedger(
            default_construction_chart(),
            entity_id=ENTITY,
        )

    def test_balanced_posting(
        self,
    ):
        ledger = self.ledger()

        entry = ledger.create_entry(
            entry_date=DAY,
            source_type="manual",
            source_id="1",
            memo="customer payment",
            lines=(
                JournalLine(
                    account_code="1000",
                    debit=Decimal(
                        "1000.00"
                    ),
                ),
                JournalLine(
                    account_code="4000",
                    credit=Decimal(
                        "1000.00"
                    ),
                ),
            ),
        )

        ledger.post(
            entry
        )

        trial = ledger.trial_balance()

        self.assertTrue(
            trial.balanced
        )

        self.assertEqual(
            trial.total_debits,
            Decimal(
                "1000.00"
            ),
        )

        statement = (
            ledger.income_statement()
        )

        self.assertEqual(
            statement.revenue,
            Decimal(
                "1000.00"
            ),
        )

        balance_sheet = (
            ledger.balance_sheet()
        )

        self.assertTrue(
            balance_sheet.balanced
        )

    def test_unbalanced_entry_rejected(
        self,
    ):
        ledger = self.ledger()

        entry = ledger.create_entry(
            entry_date=DAY,
            source_type="manual",
            source_id="bad",
            memo="bad",
            lines=(
                JournalLine(
                    account_code="1000",
                    debit=100,
                ),
                JournalLine(
                    account_code="4000",
                    credit=99,
                ),
            ),
        )

        with self.assertRaises(
            AccountingInvariantError
        ):
            ledger.post(
                entry
            )

    def test_source_idempotency(
        self,
    ):
        ledger = self.ledger()

        entry = ledger.create_entry(
            entry_date=DAY,
            source_type="bank",
            source_id="tx-1",
            memo="test",
            lines=(
                JournalLine(
                    "1000",
                    debit=100,
                ),
                JournalLine(
                    "4000",
                    credit=100,
                ),
            ),
        )

        first = ledger.post(
            entry
        )

        second = ledger.post(
            entry
        )

        self.assertEqual(
            first.entry_id,
            second.entry_id,
        )

        self.assertEqual(
            len(
                ledger.entries()
            ),
            1,
        )

    def test_cross_entity_post_rejected(
        self,
    ):
        ledger = self.ledger()

        with self.assertRaises(
            EntityIsolationError
        ):
            ledger.create_entry(
                entity_id="personal-books",
                entry_date=DAY,
                source_type="manual",
                source_id="wrong-entity",
                memo="wrong",
                lines=(
                    JournalLine(
                        "1000",
                        debit=100,
                    ),
                    JournalLine(
                        "4000",
                        credit=100,
                    ),
                ),
            )


class BankAndBookkeepingTests(
    unittest.TestCase
):
    def setUp(
        self,
    ):
        self.system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY,
            )
        )

        self.system.add_classification_rule(
            ClassificationRule(
                rule_id="concrete-material",
                contains_any=(
                    "READY MIX SUPPLY",
                ),
                kind=(
                    TransactionKind.EXPENSE
                ),
                counter_account_code="5010",
                confidence=0.98,
                direction=(
                    BankDirection.OUTFLOW
                ),
                project_required=True,
                default_cost_code=(
                    "03-30-00"
                ),
                tax_category=(
                    "direct_material"
                ),
            )
        )

        self.system.add_classification_rule(
            ClassificationRule(
                rule_id="customer-revenue",
                contains_any=(
                    "CUSTOMER ACH",
                ),
                kind=(
                    TransactionKind.REVENUE
                ),
                counter_account_code="4000",
                confidence=0.99,
                direction=(
                    BankDirection.INFLOW
                ),
            )
        )

        self.system.add_classification_rule(
            ClassificationRule(
                rule_id="card-payment",
                contains_any=(
                    "CARD PAYMENT",
                ),
                kind=(
                    TransactionKind
                    .CREDIT_CARD_PAYMENT
                ),
                counter_account_code="2100",
                confidence=0.99,
                direction=(
                    BankDirection.OUTFLOW
                ),
            )
        )

        self.system.add_classification_rule(
            ClassificationRule(
                rule_id="loan-payment",
                contains_any=(
                    "AUTO LOAN",
                ),
                kind=(
                    TransactionKind.LOAN_PAYMENT
                ),
                counter_account_code="2400",
                confidence=0.99,
                direction=(
                    BankDirection.OUTFLOW
                ),
            )
        )

    def raw(
        self,
        *,
        transaction_id,
        signed_amount,
        description,
        entity_id=ENTITY,
    ):
        return RawBankTransaction(
            entity_id=(
                entity_id
            ),
            provider="test-bank",
            transaction_id=(
                transaction_id
            ),
            account_id="checking-1",
            posted_date=DAY,
            signed_amount=Decimal(
                str(
                    signed_amount
                )
            ),
            description=description,
            merchant_name=description,
        )

    def test_feed_deduplication(
        self,
    ):
        raw = self.raw(
            transaction_id="a",
            signed_amount=-100,
            description="READY MIX SUPPLY",
        )

        accepted, duplicates = (
            self.system
            .ingest_raw_transactions(
                (
                    raw,
                    raw,
                )
            )
        )

        self.assertEqual(
            len(
                accepted
            ),
            1,
        )

        self.assertEqual(
            len(
                duplicates
            ),
            1,
        )

    def test_cross_entity_ingestion_rejected(
        self,
    ):
        with self.assertRaises(
            EntityIsolationError
        ):
            self.system.ingest_raw_transactions(
                (
                    self.raw(
                        transaction_id="personal-1",
                        signed_amount=-100,
                        description="PERSONAL",
                        entity_id="personal-books",
                    ),
                )
            )

    def test_high_confidence_expense_auto_posts(
        self,
    ):
        accepted, _ = (
            self.system
            .ingest_raw_transactions(
                (
                    self.raw(
                        transaction_id="expense-1",
                        signed_amount=-2500,
                        description=(
                            "READY MIX SUPPLY"
                        ),
                    ),
                )
            )
        )

        decision = (
            self.system
            .process_transaction(
                accepted[
                    0
                ],
                bank_account_code="1000",
                project_id="job-001",
            )
        )

        self.assertEqual(
            decision.status,
            PostingStatus.AUTO_POSTED,
        )

        self.assertEqual(
            self.system.ledger
            .account_balance(
                "5010"
            ),
            Decimal(
                "2500.00"
            ),
        )

        self.assertTrue(
            self.system.ledger
            .trial_balance()
            .balanced
        )

    def test_revenue_auto_posts(
        self,
    ):
        accepted, _ = (
            self.system
            .ingest_raw_transactions(
                (
                    self.raw(
                        transaction_id="income-1",
                        signed_amount=5000,
                        description=(
                            "CUSTOMER ACH"
                        ),
                    ),
                )
            )
        )

        decision = (
            self.system
            .process_transaction(
                accepted[
                    0
                ],
                bank_account_code="1000",
            )
        )

        self.assertEqual(
            decision.status,
            PostingStatus.AUTO_POSTED,
        )

        statement = (
            self.system.ledger
            .income_statement()
        )

        self.assertEqual(
            statement.revenue,
            Decimal(
                "5000.00"
            ),
        )

    def test_credit_card_payment_not_double_counted_as_expense(
        self,
    ):
        accepted, _ = (
            self.system
            .ingest_raw_transactions(
                (
                    self.raw(
                        transaction_id="cc-1",
                        signed_amount=-800,
                        description=(
                            "CARD PAYMENT"
                        ),
                    ),
                )
            )
        )

        decision = (
            self.system
            .process_transaction(
                accepted[
                    0
                ],
                bank_account_code="1000",
            )
        )

        self.assertEqual(
            decision.status,
            PostingStatus.AUTO_POSTED,
        )

        statement = (
            self.system.ledger
            .income_statement()
        )

        self.assertEqual(
            statement.operating_expense,
            Decimal(
                "0.00"
            ),
        )

    def test_loan_payment_requires_split_review(
        self,
    ):
        accepted, _ = (
            self.system
            .ingest_raw_transactions(
                (
                    self.raw(
                        transaction_id="loan-1",
                        signed_amount=-700,
                        description=(
                            "AUTO LOAN"
                        ),
                    ),
                )
            )
        )

        decision = (
            self.system
            .process_transaction(
                accepted[
                    0
                ],
                bank_account_code="1000",
            )
        )

        self.assertEqual(
            decision.status,
            PostingStatus.REVIEW_REQUIRED,
        )

    def test_unknown_goes_to_review(
        self,
    ):
        accepted, _ = (
            self.system
            .ingest_raw_transactions(
                (
                    self.raw(
                        transaction_id="unknown",
                        signed_amount=-75,
                        description="UNKNOWN XYZ",
                    ),
                )
            )
        )

        decision = (
            self.system
            .process_transaction(
                accepted[
                    0
                ],
                bank_account_code="1000",
            )
        )

        self.assertEqual(
            decision.status,
            PostingStatus.REVIEW_REQUIRED,
        )


class ReconciliationTests(
    unittest.TestCase
):
    def test_bank_reconciles_to_auto_posted_entry(
        self,
    ):
        system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY,
            )
        )

        system.add_classification_rule(
            ClassificationRule(
                rule_id="revenue",
                contains_any=(
                    "CLIENT",
                ),
                kind=(
                    TransactionKind.REVENUE
                ),
                counter_account_code="4000",
                confidence=0.99,
                direction=(
                    BankDirection.INFLOW
                ),
            )
        )

        raw = RawBankTransaction(
            entity_id=ENTITY,
            provider="bank",
            transaction_id="client-1",
            account_id="acct",
            posted_date=DAY,
            signed_amount=Decimal(
                "1000"
            ),
            description="CLIENT",
        )

        accepted, _ = (
            system.ingest_raw_transactions(
                (
                    raw,
                )
            )
        )

        system.process_transaction(
            accepted[
                0
            ],
            bank_account_code="1000",
        )

        report = (
            ReconciliationEngine()
            .reconcile(
                transactions=(
                    accepted
                ),
                ledger=(
                    system.ledger
                ),
                bank_account_code="1000",
            )
        )

        self.assertTrue(
            report.reconciled
        )

        self.assertEqual(
            report.matched[
                0
            ].confidence,
            1.0,
        )


class JobCostTests(
    unittest.TestCase
):
    def test_margin_erosion_detected(
        self,
    ):
        snapshot = (
            JobCostAnalyzer()
            .analyze(
                JobFinancialState(
                    project_id="job-a",
                    original_contract=(
                        Decimal(
                            "1000000"
                        )
                    ),
                    approved_change_orders=(
                        Decimal(
                            "50000"
                        )
                    ),
                    original_estimated_cost=(
                        Decimal(
                            "800000"
                        )
                    ),
                    actual_cost_to_date=(
                        Decimal(
                            "600000"
                        )
                    ),
                    committed_remaining=(
                        Decimal(
                            "300000"
                        )
                    ),
                    forecast_uncommitted_cost=(
                        Decimal(
                            "100000"
                        )
                    ),
                    earned_value=(
                        Decimal(
                            "500000"
                        )
                    ),
                    planned_value=(
                        Decimal(
                            "600000"
                        )
                    ),
                    cash_paid=(
                        Decimal(
                            "600000"
                        )
                    ),
                    commitments_due_before_collections=(
                        Decimal(
                            "150000"
                        )
                    ),
                    cash_collected=(
                        Decimal(
                            "500000"
                        )
                    ),
                )
            )
        )

        self.assertGreater(
            snapshot.margin_erosion,
            0.05,
        )

        self.assertIn(
            snapshot.risk,
            {
                CashRisk.MODERATE,
                CashRisk.HIGH,
                CashRisk.CRITICAL,
            },
        )

        self.assertEqual(
            snapshot.cash_exposure,
            Decimal(
                "250000.00"
            ),
        )


class CashTests(
    unittest.TestCase
):
    def test_cash_runway_and_conservative_forecast(
        self,
    ):
        forecast = (
            CashFlowForecaster()
            .forecast(
                starting_cash=50000,
                as_of=DAY,
                events=(
                    CashEvent(
                        event_date=(
                            DAY
                            + timedelta(
                                days=7
                            )
                        ),
                        amount=(
                            Decimal(
                                "30000"
                            )
                        ),
                        label="collection",
                        confidence=0.50,
                    ),
                    CashEvent(
                        event_date=(
                            DAY
                            + timedelta(
                                days=10
                            )
                        ),
                        amount=(
                            Decimal(
                                "-40000"
                            )
                        ),
                        label="payroll",
                        confidence=1.0,
                    ),
                ),
                average_daily_net_burn=(
                    2000
                ),
            )
        )

        self.assertAlmostEqual(
            forecast.runway_days,
            25.0,
        )

        self.assertIn(
            forecast.risk,
            {
                CashRisk.HIGH,
                CashRisk.CRITICAL,
            },
        )


class AnomalyTests(
    unittest.TestCase
):
    def test_possible_duplicate_detected(
        self,
    ):
        system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY,
            )
        )

        raw_rows = (
            RawBankTransaction(
                entity_id=ENTITY,
                provider="bank",
                transaction_id="a",
                account_id="acct",
                posted_date=DAY,
                signed_amount=Decimal(
                    "-500"
                ),
                description="SUPPLIER",
                merchant_name="SUPPLIER",
            ),

            RawBankTransaction(
                entity_id=ENTITY,
                provider="bank",
                transaction_id="b",
                account_id="acct",
                posted_date=DAY,
                signed_amount=Decimal(
                    "-500"
                ),
                description="SUPPLIER",
                merchant_name="SUPPLIER",
            ),
        )

        normalizer = (
            system.bank_ingestor.normalizer
        )

        transactions = tuple(
            normalizer.normalize(
                raw
            )
            for raw
            in raw_rows
        )

        anomalies = (
            FinancialAnomalyDetector()
            .detect(
                transactions
            )
        )

        self.assertTrue(
            any(
                anomaly.anomaly_type
                == "possible_duplicate"
                for anomaly
                in anomalies
            )
        )


class CapitalTests(
    unittest.TestCase
):
    def test_operating_reserve_blocks_overdeployment(
        self,
    ):
        plan = (
            CapitalAllocator()
            .rank(
                available_cash=100000,
                required_operating_reserve=80000,
                options=(
                    CapitalOption(
                        option_id="equipment",
                        name="Equipment",
                        required_capital=Decimal(
                            "50000"
                        ),
                        expected_return_rate=0.20,
                        downside_loss_rate=0.10,
                        liquidity_days=365,
                        strategic_value=0.90,
                        tax_efficiency=0.50,
                        risk_score=0.35,
                    ),
                    CapitalOption(
                        option_id="marketing",
                        name="Marketing",
                        required_capital=Decimal(
                            "10000"
                        ),
                        expected_return_rate=0.30,
                        downside_loss_rate=0.15,
                        liquidity_days=30,
                        strategic_value=0.80,
                        tax_efficiency=0.30,
                        risk_score=0.40,
                    ),
                ),
            )
        )

        mapping = {
            row.option_id:
                row
            for row
            in plan.recommendations
        }

        self.assertFalse(
            mapping[
                "equipment"
            ].deployable
        )

        self.assertTrue(
            mapping[
                "marketing"
            ].deployable
        )


class ComplianceTests(
    unittest.TestCase
):
    def test_upcoming_and_overdue(
        self,
    ):
        calendar = (
            ComplianceCalendar()
        )

        calendar.add(
            ComplianceObligation(
                obligation_id="future",
                entity_id=ENTITY,
                name="Future Filing",
                authority="Authority",
                due_date=(
                    DAY
                    + timedelta(
                        days=20
                    )
                ),
                rule_version="v1",
                source_reference="source",
            )
        )

        calendar.add(
            ComplianceObligation(
                obligation_id="late",
                entity_id=ENTITY,
                name="Late Filing",
                authority="Authority",
                due_date=(
                    DAY
                    - timedelta(
                        days=1
                    )
                ),
                rule_version="v1",
                source_reference="source",
            )
        )

        self.assertEqual(
            len(
                calendar.upcoming(
                    as_of=DAY,
                    days=30,
                    entity_id=ENTITY,
                )
            ),
            1,
        )

        self.assertEqual(
            len(
                calendar.overdue(
                    as_of=DAY,
                    entity_id=ENTITY,
                )
            ),
            1,
        )


class PersistenceTests(
    unittest.TestCase
):
    def test_financial_records_persist(
        self,
    ):
        store = FakeStore()

        repository = (
            FinancialRepository(
                store,
                tenant_id="tenant",
            )
        )

        system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY,
                repository=repository,
            )
        )

        system.add_classification_rule(
            ClassificationRule(
                rule_id="rev",
                contains_any=(
                    "CLIENT",
                ),
                kind=(
                    TransactionKind.REVENUE
                ),
                counter_account_code="4000",
                confidence=0.99,
                direction=(
                    BankDirection.INFLOW
                ),
            )
        )

        accepted, _ = (
            system.ingest_raw_transactions(
                (
                    RawBankTransaction(
                        entity_id=ENTITY,
                        provider="bank",
                        transaction_id="persist",
                        account_id="acct",
                        posted_date=DAY,
                        signed_amount=(
                            Decimal(
                                "1000"
                            )
                        ),
                        description="CLIENT",
                    ),
                )
            )
        )

        system.process_transaction(
            accepted[
                0
            ],
            bank_account_code="1000",
        )

        entity_types = {
            key[
                1
            ]
            for key
            in store.entities
        }

        self.assertIn(
            "goat.finance.bank_transaction",
            entity_types,
        )

        self.assertIn(
            "goat.finance.journal_entry",
            entity_types,
        )

        self.assertIn(
            "goat.finance.bookkeeping_decision",
            entity_types,
        )


class SuperintelligenceIntegrationTests(
    unittest.TestCase
):
    def test_financial_experts_drive_corrective_action(
        self,
    ):
        kernel = (
            CognitiveKernel()
        )

        install_financial_experts(
            kernel
        )

        decision = kernel.reason(
            domain="financial_health",
            question=(
                "Is financial position healthy?"
            ),
            context={
                "runway_days":
                    20,
                "projected_margin":
                    0.02,
                "margin_erosion":
                    0.14,
                "unreconciled_transactions":
                    2,
                "review_queue":
                    1,
            },
            evidence=(
                "cash-forecast",
                "job-cost",
            ),
            requested_autonomy=(
                AutonomyLevel.RECOMMEND
            ),
        )

        self.assertEqual(
            decision.recommendation,
            "corrective_action",
        )

        self.assertGreater(
            decision.confidence,
            0.75,
        )


class FinancialStressTests(
    unittest.TestCase
):
    def test_5000_balanced_entries(
        self,
    ):
        ledger = (
            GeneralLedger(
                default_construction_chart(),
                entity_id=ENTITY,
            )
        )

        for index in range(
            5000
        ):
            amount = money(
                (
                    index
                    % 100
                )
                + 1
            )

            entry = (
                ledger.create_entry(
                    entry_date=DAY,
                    source_type="stress",
                    source_id=(
                        f"stress-{index}"
                    ),
                    memo="stress",
                    lines=(
                        JournalLine(
                            account_code="1000",
                            debit=amount,
                        ),
                        JournalLine(
                            account_code="4000",
                            credit=amount,
                        ),
                    ),
                )
            )

            ledger.post(
                entry
            )

        trial = (
            ledger.trial_balance()
        )

        self.assertTrue(
            trial.balanced
        )

        self.assertTrue(
            ledger.balance_sheet()
            .balanced
        )

        self.assertEqual(
            len(
                ledger.entries()
            ),
            5000,
        )


if __name__ == "__main__":
    unittest.main()
