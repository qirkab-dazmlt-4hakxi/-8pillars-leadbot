from __future__ import annotations

import os
import unittest

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from leadbot_v2.goat.financial_intelligence import (
    BankDirection,
    ClassificationRule,
    FinancialIntelligenceSystem,
    JobFinancialState,
    RawBankTransaction,
    ReconciliationEngine,
    TransactionKind,
)

from leadbot_v2.goat.financial_operations import (
    AdaptiveCostCoder,
    CloseSeverity,
    CollectionsPrioritizer,
    EnvironmentSecretResolver,
    ExternalAccount,
    ExternalTransaction,
    FinancialOperationsRepository,
    FinancialOperationsService,
    Invoice,
    InvoiceLine,
    OpenItemStatus,
    Payable,
    ProviderCapability,
    ProviderRegistration,
    ProviderTransactionPage,
    Receipt,
    Receivable,
    SecretRef,
    SecretResolutionError,
    SimulatedReadOnlyProvider,
)

from leadbot_v2.goat.financial_operations.models import (
    SurveillanceSeverity,
)


DAY = date(
    2026,
    8,
    17,
)

ENTITY = (
    "twins-development"
)


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


class SecretTests(
    unittest.TestCase
):
    def test_environment_secret_resolution(
        self,
    ):
        key = (
            "GOAT_TEST_FINANCE_SECRET"
        )

        os.environ[
            key
        ] = "secret-value"

        try:
            value = (
                EnvironmentSecretResolver()
                .resolve(
                    SecretRef(
                        key
                    )
                )
            )

            self.assertEqual(
                value,
                "secret-value",
            )

        finally:
            os.environ.pop(
                key,
                None,
            )

    def test_missing_secret_fails_closed(
        self,
    ):
        os.environ.pop(
            "GOAT_MISSING_SECRET",
            None,
        )

        with self.assertRaises(
            SecretResolutionError
        ):
            (
                EnvironmentSecretResolver()
                .resolve(
                    SecretRef(
                        "GOAT_MISSING_SECRET"
                    )
                )
            )


class ProviderAndSyncTests(
    unittest.TestCase
):
    def system(
        self,
    ):
        return FinancialIntelligenceSystem(
            entity_id=ENTITY
        )

    def service(
        self,
        *,
        pages,
    ):
        system = self.system()

        service = (
            FinancialOperationsService(
                entity_id=ENTITY,
                financial_system=(
                    system
                ),
                secret_resolver=(
                    EnvironmentSecretResolver()
                ),
            )
        )

        account = ExternalAccount(
            provider_name=(
                "goat-simulated-finance"
            ),
            entity_id=ENTITY,
            external_account_id=(
                "checking"
            ),
            display_name=(
                "Operating"
            ),
            account_type=(
                "checking"
            ),
            current_balance=(
                Decimal(
                    "10000"
                )
            ),
        )

        provider = (
            SimulatedReadOnlyProvider(
                accounts=(
                    account,
                ),
                pages=pages,
            )
        )

        service.providers.register(
            registration=(
                ProviderRegistration(
                    provider_name=(
                        provider.provider_name
                    ),
                    capabilities=frozenset(
                        {
                            ProviderCapability
                            .ACCOUNTS_READ,

                            ProviderCapability
                            .TRANSACTIONS_READ,
                        }
                    ),
                )
            ),
            provider=provider,
        )

        return (
            system,
            service,
        )

    def test_pending_is_staged_not_forwarded(
        self,
    ):
        pending = ExternalTransaction(
            provider_name=(
                "goat-simulated-finance"
            ),
            entity_id=ENTITY,
            external_account_id="checking",
            external_transaction_id="tx-1",
            posted_date=DAY,
            signed_amount=(
                Decimal(
                    "-100"
                )
            ),
            description="MATERIAL",
            pending=True,
        )

        page = ProviderTransactionPage(
            transactions=(
                pending,
            ),
            next_cursor="c1",
            has_more=False,
        )

        system, service = self.service(
            pages={
                (
                    ENTITY,
                    "checking",
                    None,
                ):
                    page,
            }
        )

        result = service.sync_provider(
            provider_name=(
                "goat-simulated-finance"
            ),
            start_date=DAY,
            end_date=DAY,
        )

        self.assertEqual(
            result.staged_pending,
            1,
        )

        self.assertEqual(
            result.accepted_posted,
            0,
        )

        self.assertEqual(
            len(
                system.transactions
            ),
            0,
        )

    def test_posted_transaction_forwarded_once(
        self,
    ):
        posted = ExternalTransaction(
            provider_name=(
                "goat-simulated-finance"
            ),
            entity_id=ENTITY,
            external_account_id="checking",
            external_transaction_id="tx-1",
            posted_date=DAY,
            signed_amount=(
                Decimal(
                    "-100"
                )
            ),
            description="MATERIAL",
            pending=False,
        )

        first = ProviderTransactionPage(
            transactions=(
                posted,
            ),
            next_cursor="done",
            has_more=False,
        )

        second = ProviderTransactionPage(
            transactions=(
                posted,
            ),
            next_cursor="done2",
            has_more=False,
        )

        system, service = self.service(
            pages={
                (
                    ENTITY,
                    "checking",
                    None,
                ):
                    first,

                (
                    ENTITY,
                    "checking",
                    "done",
                ):
                    second,
            }
        )

        one = service.sync_provider(
            provider_name=(
                "goat-simulated-finance"
            ),
            start_date=DAY,
            end_date=DAY,
        )

        two = service.sync_provider(
            provider_name=(
                "goat-simulated-finance"
            ),
            start_date=DAY,
            end_date=DAY,
        )

        self.assertEqual(
            one.accepted_posted,
            1,
        )

        self.assertEqual(
            two.duplicates,
            1,
        )

        self.assertEqual(
            len(
                system.transactions
            ),
            1,
        )

    def test_changed_posted_transaction_quarantined_as_correction(
        self,
    ):
        original = ExternalTransaction(
            provider_name=(
                "goat-simulated-finance"
            ),
            entity_id=ENTITY,
            external_account_id="checking",
            external_transaction_id="tx-correction",
            posted_date=DAY,
            signed_amount=(
                Decimal(
                    "-100"
                )
            ),
            description="VENDOR",
            pending=False,
        )

        changed = ExternalTransaction(
            provider_name=(
                "goat-simulated-finance"
            ),
            entity_id=ENTITY,
            external_account_id="checking",
            external_transaction_id="tx-correction",
            posted_date=DAY,
            signed_amount=(
                Decimal(
                    "-125"
                )
            ),
            description="VENDOR",
            pending=False,
            revision_token="revision-2",
        )

        system, service = self.service(
            pages={
                (
                    ENTITY,
                    "checking",
                    None,
                ):
                    ProviderTransactionPage(
                        transactions=(
                            original,
                        ),
                        next_cursor="next",
                        has_more=False,
                    ),

                (
                    ENTITY,
                    "checking",
                    "next",
                ):
                    ProviderTransactionPage(
                        transactions=(
                            changed,
                        ),
                        next_cursor="final",
                        has_more=False,
                    ),
            }
        )

        service.sync_provider(
            provider_name=(
                "goat-simulated-finance"
            ),
            start_date=DAY,
            end_date=DAY,
        )

        result = service.sync_provider(
            provider_name=(
                "goat-simulated-finance"
            ),
            start_date=DAY,
            end_date=DAY,
        )

        self.assertEqual(
            len(
                result.corrections
            ),
            1,
        )

        self.assertEqual(
            len(
                system.transactions
            ),
            1,
        )


class DocumentTests(
    unittest.TestCase
):
    def test_invoice_matches_bank_transaction(
        self,
    ):
        system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY
            )
        )

        raw = RawBankTransaction(
            entity_id=ENTITY,
            provider="bank",
            transaction_id="purchase-1",
            account_id="checking",
            posted_date=(
                DAY
                + timedelta(
                    days=1
                )
            ),
            signed_amount=(
                Decimal(
                    "-2500"
                )
            ),
            description=(
                "ABC READY MIX"
            ),
            merchant_name=(
                "ABC Ready Mix"
            ),
        )

        transactions, _ = (
            system
            .ingest_raw_transactions(
                (
                    raw,
                )
            )
        )

        service = (
            FinancialOperationsService(
                entity_id=ENTITY,
                financial_system=system,
                secret_resolver=(
                    EnvironmentSecretResolver()
                ),
            )
        )

        invoice = Invoice(
            invoice_id="inv-1",
            entity_id=ENTITY,
            vendor_id="ABC Ready Mix",
            invoice_number="100",
            invoice_date=DAY,
            due_date=(
                DAY
                + timedelta(
                    days=30
                )
            ),
            amount=(
                Decimal(
                    "2500"
                )
            ),
        )

        matches = (
            service.documents
            .match_invoice(
                invoice,
                transactions,
                vendor_display_name=(
                    "ABC Ready Mix"
                ),
            )
        )

        self.assertGreater(
            matches[
                0
            ].confidence,
            0.90,
        )


class APARTests(
    unittest.TestCase
):
    def service(
        self,
    ):
        system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY
            )
        )

        return FinancialOperationsService(
            entity_id=ENTITY,
            financial_system=system,
            secret_resolver=(
                EnvironmentSecretResolver()
            ),
        )

    def test_ar_aging_and_collection(
        self,
    ):
        service = self.service()

        item = Receivable(
            receivable_id="ar-1",
            entity_id=ENTITY,
            customer_id="customer",
            invoice_number="100",
            invoice_date=(
                DAY
                - timedelta(
                    days=60
                )
            ),
            due_date=(
                DAY
                - timedelta(
                    days=40
                )
            ),
            original_amount=(
                Decimal(
                    "10000"
                )
            ),
            outstanding_amount=(
                Decimal(
                    "10000"
                )
            ),
            collection_probability=0.8,
        )

        service.receivables.add(
            item
        )

        aging = (
            service.receivables
            .aging(
                as_of=DAY
            )
        )

        self.assertEqual(
            aging.days_31_60,
            Decimal(
                "10000.00"
            ),
        )

        updated = (
            service.receivables
            .apply_collection(
                "ar-1",
                Decimal(
                    "4000"
                ),
            )
        )

        self.assertEqual(
            updated.outstanding_amount,
            Decimal(
                "6000.00"
            ),
        )

        self.assertEqual(
            updated.status,
            OpenItemStatus.PARTIAL,
        )

    def test_ap_generates_negative_cash_event(
        self,
    ):
        service = self.service()

        item = Payable(
            payable_id="ap-1",
            entity_id=ENTITY,
            vendor_id="vendor",
            invoice_number="200",
            invoice_date=DAY,
            due_date=(
                DAY
                + timedelta(
                    days=10
                )
            ),
            original_amount=(
                Decimal(
                    "2500"
                )
            ),
            outstanding_amount=(
                Decimal(
                    "2500"
                )
            ),
        )

        service.payables.add(
            item
        )

        event = (
            service.payables
            .expected_cash_events()[
                0
            ]
        )

        self.assertEqual(
            event.amount,
            Decimal(
                "-2500.00"
            ),
        )


class CostCodingTests(
    unittest.TestCase
):
    def test_human_approved_training_and_prediction(
        self,
    ):
        coder = AdaptiveCostCoder(
            minimum_examples=4,
            auto_accept_threshold=0.70,
        )

        examples = (
            (
                "ready mix concrete delivery",
                "ABC Ready Mix",
                "03-30-CONCRETE",
            ),
            (
                "concrete pump and ready mix",
                "ABC Ready Mix",
                "03-30-CONCRETE",
            ),
            (
                "rebar steel reinforcing bars",
                "Steel Supply",
                "03-20-REBAR",
            ),
            (
                "reinforcing steel rebar delivery",
                "Steel Supply",
                "03-20-REBAR",
            ),
            (
                "concrete mix 4000 psi",
                "Concrete Plant",
                "03-30-CONCRETE",
            ),
            (
                "grade 60 rebar",
                "Steel Supply",
                "03-20-REBAR",
            ),
        )

        for (
            description,
            merchant,
            cost_code,
        ) in examples:
            coder.learn_approved(
                description=(
                    description
                ),
                merchant_name=(
                    merchant
                ),
                cost_code=(
                    cost_code
                ),
            )

        prediction = coder.predict(
            description=(
                "ready mix concrete 4000 psi"
            ),
            merchant_name=(
                "ABC Ready Mix"
            ),
        )

        self.assertEqual(
            prediction.label,
            "03-30-CONCRETE",
        )

        self.assertGreater(
            prediction.confidence,
            0.70,
        )


class CollectionsTests(
    unittest.TestCase
):
    def test_large_old_receivable_prioritized(
        self,
    ):
        items = (
            Receivable(
                receivable_id="small",
                entity_id=ENTITY,
                customer_id="a",
                invoice_number="1",
                invoice_date=DAY,
                due_date=(
                    DAY
                    - timedelta(
                        days=5
                    )
                ),
                original_amount=(
                    Decimal(
                        "1000"
                    )
                ),
                outstanding_amount=(
                    Decimal(
                        "1000"
                    )
                ),
                collection_probability=0.95,
            ),

            Receivable(
                receivable_id="large-old",
                entity_id=ENTITY,
                customer_id="b",
                invoice_number="2",
                invoice_date=DAY,
                due_date=(
                    DAY
                    - timedelta(
                        days=75
                    )
                ),
                original_amount=(
                    Decimal(
                        "25000"
                    )
                ),
                outstanding_amount=(
                    Decimal(
                        "25000"
                    )
                ),
                collection_probability=0.70,
            ),
        )

        ranked = (
            CollectionsPrioritizer()
            .rank(
                items,
                as_of=DAY,
            )
        )

        self.assertEqual(
            ranked[
                0
            ].receivable_id,
            "large-old",
        )


class CloseTests(
    unittest.TestCase
):
    def test_close_blocks_on_bookkeeping_review(
        self,
    ):
        system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY
            )
        )

        service = (
            FinancialOperationsService(
                entity_id=ENTITY,
                financial_system=system,
                secret_resolver=(
                    EnvironmentSecretResolver()
                ),
            )
        )

        system.add_classification_rule(
            ClassificationRule(
                rule_id="loan",
                contains_any=(
                    "LOAN",
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

        accepted, _ = (
            system.ingest_raw_transactions(
                (
                    RawBankTransaction(
                        entity_id=ENTITY,
                        provider="bank",
                        transaction_id="loan-review",
                        account_id="checking",
                        posted_date=DAY,
                        signed_amount=(
                            Decimal(
                                "-1000"
                            )
                        ),
                        description="LOAN",
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

        fake_reconciliation = (
            SimpleNamespace(
                reconciled=True
            )
        )

        report = service.close_period(
            period_end=DAY,
            reconciliation_report=(
                fake_reconciliation
            ),
        )

        self.assertFalse(
            report.closable
        )

        self.assertTrue(
            any(
                finding.severity
                is CloseSeverity.BLOCKING
                for finding
                in report.findings
            )
        )

    def test_clean_close_passes(
        self,
    ):
        system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY
            )
        )

        service = (
            FinancialOperationsService(
                entity_id=ENTITY,
                financial_system=system,
                secret_resolver=(
                    EnvironmentSecretResolver()
                ),
            )
        )

        report = service.close_period(
            period_end=DAY,
            reconciliation_report=(
                SimpleNamespace(
                    reconciled=True
                )
            ),
        )

        self.assertTrue(
            report.closable
        )


class SurveillanceTests(
    unittest.TestCase
):
    def test_margin_erosion_surfaces_high_alert(
        self,
    ):
        system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY
            )
        )

        service = (
            FinancialOperationsService(
                entity_id=ENTITY,
                financial_system=system,
                secret_resolver=(
                    EnvironmentSecretResolver()
                ),
            )
        )

        snapshot = (
            system.jobcost.analyze(
                JobFinancialState(
                    project_id="project",
                    original_contract=(
                        Decimal(
                            "1000000"
                        )
                    ),
                    approved_change_orders=(
                        Decimal(
                            "0"
                        )
                    ),
                    original_estimated_cost=(
                        Decimal(
                            "750000"
                        )
                    ),
                    actual_cost_to_date=(
                        Decimal(
                            "650000"
                        )
                    ),
                    committed_remaining=(
                        Decimal(
                            "250000"
                        )
                    ),
                    forecast_uncommitted_cost=(
                        Decimal(
                            "50000"
                        )
                    ),
                    earned_value=(
                        Decimal(
                            "600000"
                        )
                    ),
                    planned_value=(
                        Decimal(
                            "700000"
                        )
                    ),
                    cash_paid=(
                        Decimal(
                            "600000"
                        )
                    ),
                    commitments_due_before_collections=(
                        Decimal(
                            "200000"
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

        alert = (
            service.profitability
            .evaluate(
                snapshot
            )
        )

        self.assertIn(
            alert.severity,
            {
                SurveillanceSeverity.HIGH,
                SurveillanceSeverity.CRITICAL,
            },
        )


class PersistenceTests(
    unittest.TestCase
):
    def test_sync_cursor_and_close_report_persist(
        self,
    ):
        store = FakeStore()

        repository = (
            FinancialOperationsRepository(
                store,
                tenant_id="tenant",
            )
        )

        system = (
            FinancialIntelligenceSystem(
                entity_id=ENTITY
            )
        )

        service = (
            FinancialOperationsService(
                entity_id=ENTITY,
                financial_system=system,
                secret_resolver=(
                    EnvironmentSecretResolver()
                ),
                repository=repository,
            )
        )

        provider = (
            SimulatedReadOnlyProvider(
                accounts=(
                    ExternalAccount(
                        provider_name=(
                            "goat-simulated-finance"
                        ),
                        entity_id=ENTITY,
                        external_account_id="acct",
                        display_name="Checking",
                        account_type="checking",
                    ),
                ),
                pages={
                    (
                        ENTITY,
                        "acct",
                        None,
                    ):
                        ProviderTransactionPage(
                            transactions=(),
                            next_cursor="cursor-1",
                            has_more=False,
                        ),
                },
            )
        )

        service.providers.register(
            registration=(
                ProviderRegistration(
                    provider_name=(
                        provider.provider_name
                    ),
                    capabilities=frozenset(
                        {
                            ProviderCapability
                            .ACCOUNTS_READ,

                            ProviderCapability
                            .TRANSACTIONS_READ,
                        }
                    ),
                )
            ),
            provider=provider,
        )

        service.sync_provider(
            provider_name=(
                provider.provider_name
            ),
            start_date=DAY,
            end_date=DAY,
        )

        service.close_period(
            period_end=DAY,
            reconciliation_report=(
                SimpleNamespace(
                    reconciled=True
                )
            ),
        )

        entity_types = {
            key[
                1
            ]
            for key
            in store.entities
        }

        self.assertIn(
            "goat.finance_ops.sync_cursor",
            entity_types,
        )

        self.assertIn(
            "goat.finance_ops.close_report",
            entity_types,
        )


class StressTests(
    unittest.TestCase
):
    def test_5000_cost_code_predictions(
        self,
    ):
        coder = AdaptiveCostCoder(
            minimum_examples=2,
            auto_accept_threshold=0.60,
        )

        coder.learn_approved(
            description=(
                "ready mix concrete"
            ),
            merchant_name=(
                "Concrete Plant"
            ),
            cost_code=(
                "03-CONCRETE"
            ),
        )

        coder.learn_approved(
            description=(
                "reinforcing steel rebar"
            ),
            merchant_name=(
                "Steel Supply"
            ),
            cost_code=(
                "03-REBAR"
            ),
        )

        for index in range(
            5000
        ):
            prediction = coder.predict(
                description=(
                    "ready mix concrete "
                    f"load {index}"
                ),
                merchant_name=(
                    "Concrete Plant"
                ),
            )

            self.assertEqual(
                prediction.label,
                "03-CONCRETE",
            )


if __name__ == "__main__":
    unittest.main()
