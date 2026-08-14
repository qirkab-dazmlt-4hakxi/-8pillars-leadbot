import unittest

from leadbot_v2.goat.access_control import (
    Principal,
    Role,
)
from leadbot_v2.goat.crm.service import GoatCRM
from leadbot_v2.goat.data_spine.models import (
    OpportunityStage,
)
from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
)
from leadbot_v2.goat.finance.project_finance import (
    BillStatus,
    ChangeOrderStatus,
    CostCategory,
    FinancialAuthorizationError,
    FinancialValidationError,
    InvoiceStatus,
    JournalLine,
    ProjectFinanceService,
)


TENANT = "twins-development"
BU = "twins-development"


def principal(
    user_id: str,
    role: Role,
) -> Principal:
    return Principal(
        user_id=user_id,
        tenant_id=TENANT,
        role=role,
        email=f"{user_id}@example.com",
    )


class FinancialSpineTests(unittest.TestCase):

    def setUp(self):
        self.spine = InMemoryDataSpine()
        self.crm = GoatCRM(self.spine)

        self.finance = ProjectFinanceService(
            spine=self.spine,
        )

        self.president = principal(
            "president",
            Role.PRESIDENT,
        )

        self.vp = principal(
            "vp",
            Role.VICE_PRESIDENT,
        )

        self.sales = principal(
            "sales",
            Role.SALES,
        )

        self.security = principal(
            "security",
            Role.SECURITY_ADMIN,
        )

        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="president",
            title="GOAT Test Project",
            source="BuildingConnected",
        )

        opportunity = self.crm.promote_lead(
            tenant_id=TENANT,
            actor_id="president",
            lead_id=lead.entity_id,
            estimated_value_cents=2_000_000_00,
        )

        won = self.crm.set_opportunity_stage(
            tenant_id=TENANT,
            actor_id="president",
            opportunity_id=opportunity.entity_id,
            stage=OpportunityStage.WON,
        )

        self.project = (
            self.crm
            .create_project_from_won_opportunity(
                tenant_id=TENANT,
                actor_id="president",
                opportunity_id=won.entity_id,
                contract_value_cents=2_000_000_00,
            )
        )

        self.finance.register_cost_code(
            principal=self.president,
            tenant_id=TENANT,
            business_unit_id=BU,
            code="03-3000",
            name="Cast-in-Place Concrete",
            category=CostCategory.MATERIAL,
        )

        self.finance.register_cost_code(
            principal=self.president,
            tenant_id=TENANT,
            business_unit_id=BU,
            code="03-1000",
            name="Concrete Labor",
            category=CostCategory.LABOR,
        )

    def test_sales_cannot_read_financials(self):
        with self.assertRaises(
            FinancialAuthorizationError
        ):
            self.finance.snapshot(
                principal=self.sales,
                tenant_id=TENANT,
                project_id=self.project.entity_id,
            )

    def test_security_admin_cannot_read_financials(self):
        with self.assertRaises(
            FinancialAuthorizationError
        ):
            self.finance.snapshot(
                principal=self.security,
                tenant_id=TENANT,
                project_id=self.project.entity_id,
            )

    def test_vp_can_read_financials(self):
        result = self.finance.snapshot(
            principal=self.vp,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
        )

        self.assertEqual(
            result.project_id,
            self.project.entity_id,
        )

    def test_duplicate_cost_code_rejected(self):
        with self.assertRaises(
            FinancialValidationError
        ):
            self.finance.register_cost_code(
                principal=self.president,
                tenant_id=TENANT,
                business_unit_id=BU,
                code="03-3000",
                name="Duplicate",
                category=CostCategory.MATERIAL,
            )

    def test_budget_cannot_be_negative(self):
        with self.assertRaises(
            FinancialValidationError
        ):
            self.finance.set_budget(
                principal=self.president,
                tenant_id=TENANT,
                project_id=self.project.entity_id,
                cost_code="03-3000",
                amount_cents=-1,
            )

    def test_budget_is_recorded(self):
        line = self.finance.set_budget(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            amount_cents=500_000_00,
        )

        self.assertEqual(
            line.original_budget_cents,
            500_000_00,
        )

    def test_commitment_is_tracked(self):
        item = self.finance.create_commitment(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            vendor_id="vendor-ready-mix",
            description="Ready mix concrete",
            amount_cents=350_000_00,
        )

        self.assertEqual(
            item.total_committed_cents,
            350_000_00,
        )

    def test_commitment_change_updates_total(self):
        item = self.finance.create_commitment(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            vendor_id="vendor",
            description="Concrete",
            amount_cents=100_000_00,
        )

        updated = self.finance.adjust_commitment(
            principal=self.president,
            tenant_id=TENANT,
            commitment_id=item.commitment_id,
            approved_change_cents=25_000_00,
        )

        self.assertEqual(
            updated.total_committed_cents,
            125_000_00,
        )

    def test_actual_cost_requires_source_evidence(self):
        with self.assertRaises(
            FinancialValidationError
        ):
            self.finance.record_actual_cost(
                principal=self.president,
                tenant_id=TENANT,
                project_id=self.project.entity_id,
                cost_code="03-3000",
                amount_cents=10_000_00,
                source_type="invoice",
                source_ref="",
            )

    def test_actual_cost_updates_commitment_invoiced(self):
        commitment = (
            self.finance.create_commitment(
                principal=self.president,
                tenant_id=TENANT,
                project_id=self.project.entity_id,
                cost_code="03-3000",
                vendor_id="vendor",
                description="Concrete",
                amount_cents=100_000_00,
            )
        )

        self.finance.record_actual_cost(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            amount_cents=25_000_00,
            source_type="vendor_invoice",
            source_ref="invoice://001",
            commitment_id=(
                commitment.commitment_id
            ),
        )

        updated = self.finance._commitments[
            commitment.commitment_id
        ]

        self.assertEqual(
            updated.invoiced_cents,
            25_000_00,
        )

    def test_unapproved_change_order_does_not_change_contract(self):
        change = self.finance.create_change_order(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            description="Added scope",
            revenue_change_cents=100_000_00,
            cost_change_cents=60_000_00,
        )

        self.assertEqual(
            change.status,
            ChangeOrderStatus.DRAFT,
        )

        result = self.finance.snapshot(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
        )

        self.assertEqual(
            result.revised_contract_value_cents,
            2_000_000_00,
        )

    def test_approved_change_order_changes_contract(self):
        change = self.finance.create_change_order(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            description="Added scope",
            revenue_change_cents=100_000_00,
            cost_change_cents=60_000_00,
        )

        submitted = (
            self.finance.submit_change_order(
                principal=self.president,
                tenant_id=TENANT,
                change_order_id=(
                    change.change_order_id
                ),
            )
        )

        approved = (
            self.finance.approve_change_order(
                principal=self.vp,
                tenant_id=TENANT,
                change_order_id=(
                    submitted.change_order_id
                ),
            )
        )

        self.assertEqual(
            approved.status,
            ChangeOrderStatus.APPROVED,
        )

        result = self.finance.snapshot(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
        )

        self.assertEqual(
            result.revised_contract_value_cents,
            2_100_000_00,
        )

        self.assertEqual(
            result.approved_change_cost_cents,
            60_000_00,
        )

    def test_ar_retainage_is_tracked(self):
        invoice = self.finance.create_ar_invoice(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            gross_amount_cents=100_000_00,
            retainage_cents=10_000_00,
        )

        self.assertEqual(
            invoice.net_due_cents,
            90_000_00,
        )

    def test_ar_payment_cannot_exceed_net_due(self):
        invoice = self.finance.create_ar_invoice(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            gross_amount_cents=100_000_00,
            retainage_cents=10_000_00,
        )

        with self.assertRaises(
            FinancialValidationError
        ):
            self.finance.record_ar_payment(
                principal=self.president,
                tenant_id=TENANT,
                invoice_id=invoice.invoice_id,
                amount_cents=91_000_00,
            )

    def test_ar_invoice_marks_paid(self):
        invoice = self.finance.create_ar_invoice(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            gross_amount_cents=100_000_00,
            retainage_cents=10_000_00,
        )

        paid = self.finance.record_ar_payment(
            principal=self.president,
            tenant_id=TENANT,
            invoice_id=invoice.invoice_id,
            amount_cents=90_000_00,
        )

        self.assertEqual(
            paid.status,
            InvoiceStatus.PAID,
        )

    def test_ap_payment_cannot_exceed_net_due(self):
        bill = self.finance.create_ap_bill(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            vendor_id="vendor",
            cost_code="03-3000",
            gross_amount_cents=50_000_00,
            retainage_cents=5_000_00,
        )

        with self.assertRaises(
            FinancialValidationError
        ):
            self.finance.record_ap_payment(
                principal=self.president,
                tenant_id=TENANT,
                bill_id=bill.bill_id,
                amount_cents=46_000_00,
            )

    def test_ap_bill_marks_paid(self):
        bill = self.finance.create_ap_bill(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            vendor_id="vendor",
            cost_code="03-3000",
            gross_amount_cents=50_000_00,
            retainage_cents=5_000_00,
        )

        paid = self.finance.record_ap_payment(
            principal=self.president,
            tenant_id=TENANT,
            bill_id=bill.bill_id,
            amount_cents=45_000_00,
        )

        self.assertEqual(
            paid.status,
            BillStatus.PAID,
        )

    def test_forecast_override_drives_eac(self):
        self.finance.set_budget(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            amount_cents=500_000_00,
        )

        self.finance.record_actual_cost(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            amount_cents=100_000_00,
            source_type="invoice",
            source_ref="invoice://1",
        )

        self.finance.set_forecast_to_complete(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            forecast_to_complete_cents=450_000_00,
        )

        result = self.finance.snapshot(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
        )

        self.assertEqual(
            result.estimate_at_completion_cents,
            550_000_00,
        )

    def test_balanced_journal_posts(self):
        entry = self.finance.post_journal_entry(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            description="Record owner billing",
            lines=(
                JournalLine(
                    account="Accounts Receivable",
                    debit_cents=100_000_00,
                ),
                JournalLine(
                    account="Contract Revenue",
                    credit_cents=100_000_00,
                ),
            ),
        )

        self.assertEqual(
            entry.debits_cents,
            entry.credits_cents,
        )

    def test_unbalanced_journal_is_rejected(self):
        with self.assertRaises(
            FinancialValidationError
        ):
            self.finance.post_journal_entry(
                principal=self.president,
                tenant_id=TENANT,
                project_id=self.project.entity_id,
                description="Bad journal",
                lines=(
                    JournalLine(
                        account="AR",
                        debit_cents=100_00,
                    ),
                    JournalLine(
                        account="Revenue",
                        credit_cents=90_00,
                    ),
                ),
            )

    def test_snapshot_calculates_projected_margin(self):
        self.finance.set_budget(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            amount_cents=700_000_00,
        )

        self.finance.set_budget(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-1000",
            amount_cents=500_000_00,
        )

        result = self.finance.snapshot(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
        )

        self.assertEqual(
            result.estimate_at_completion_cents,
            1_200_000_00,
        )

        self.assertEqual(
            result.projected_gross_profit_cents,
            800_000_00,
        )

        self.assertEqual(
            result.projected_margin_bps,
            4000,
        )

    def test_margin_erosion_is_detected(self):
        self.finance.set_budget(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            amount_cents=1_000_000_00,
        )

        self.finance.set_forecast_to_complete(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            forecast_to_complete_cents=1_500_000_00,
        )

        result = self.finance.snapshot(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
        )

        self.assertTrue(
            any(
                finding.code == "margin_erosion"
                for finding in result.findings
            )
        )

    def test_commitment_overrun_is_detected(self):
        commitment = (
            self.finance.create_commitment(
                principal=self.president,
                tenant_id=TENANT,
                project_id=self.project.entity_id,
                cost_code="03-3000",
                vendor_id="vendor",
                description="Concrete",
                amount_cents=10_000_00,
            )
        )

        self.finance.record_actual_cost(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            amount_cents=15_000_00,
            source_type="invoice",
            source_ref="invoice://overrun",
            commitment_id=(
                commitment.commitment_id
            ),
        )

        result = self.finance.snapshot(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
        )

        self.assertTrue(
            any(
                finding.code
                == "commitment_overrun"
                for finding in result.findings
            )
        )

    def test_financial_events_write_to_data_spine(self):
        self.finance.set_budget(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            amount_cents=500_000_00,
        )

        events = self.spine.events_for(
            tenant_id=TENANT,
            aggregate_id=self.project.entity_id,
        )

        self.assertTrue(
            any(
                event.event_type
                == "finance.budget.updated"
                for event in events
            )
        )


if __name__ == "__main__":
    unittest.main()
