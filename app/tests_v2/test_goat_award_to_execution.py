import tempfile
import unittest

from dataclasses import replace
from datetime import (
    date,
    datetime,
    timezone,
)
from pathlib import Path

from leadbot_v2.goat.execution import (
    AuditIntegrityError,
    AwardBudgetLine,
    AwardHandoff,
    AwardToExecutionService,
    ChangeEventStatus,
    CommitmentStatus,
    CommitmentType,
    CostCategory,
    DuplicateMutationConflict,
    ExecutionPersistenceBridge,
    ExecutionStatus,
    InterventionSeverity,
    MaterialReleaseStatus,
    QuantityProduction,
)

from leadbot_v2.goat.persistence.durable import (
    DurableStore,
)


UTC = timezone.utc


def award():
    return AwardHandoff(
        tenant_id="tenant",
        project_id="project-1",
        estimate_id="estimate-1",
        proposal_hash="abc123",
        project_name="GOAT Project",
        original_contract_value_cents=(
            100_000_000
        ),
        budget_lines=(
            AwardBudgetLine(
                cost_code="03-100",
                name="Concrete",
                category=(
                    CostCategory.MATERIAL
                ),
                budget_cents=(
                    40_000_000
                ),
            ),
            AwardBudgetLine(
                cost_code="26-100",
                name="Electrical",
                category=(
                    CostCategory.SUBCONTRACT
                ),
                budget_cents=(
                    25_000_000
                ),
            ),
            AwardBudgetLine(
                cost_code="22-100",
                name="Plumbing",
                category=(
                    CostCategory.SUBCONTRACT
                ),
                budget_cents=(
                    15_000_000
                ),
            ),
        ),
        awarded_at=(
            datetime(
                2026,
                8,
                15,
                tzinfo=UTC,
            )
        ),
    )


class BaseExecutionTest(
    unittest.TestCase
):

    def setUp(self):
        self.service = (
            AwardToExecutionService()
        )

        self.project = (
            self.service
            .create_from_award(
                handoff=award(),
                actor_id="president",
            )
        )

    def activate(self):
        return self.service.activate(
            tenant_id="tenant",
            project_id="project-1",
            actor_id="president",
        )


class AwardTests(
    BaseExecutionTest
):

    def test_award_handoff(self):
        self.assertEqual(
            self.project.status,
            ExecutionStatus.AWARDED,
        )

        self.assertEqual(
            len(
                self.project
                .budget_lines
            ),
            3,
        )

    def test_award_creates_audit(self):
        self.assertEqual(
            len(
                self.project.audit
            ),
            1,
        )

        self.assertTrue(
            self.service
            .verify_audit_chain(
                tenant_id="tenant",
                project_id="project-1",
            )
        )

    def test_activate(self):
        project = self.activate()

        self.assertEqual(
            project.status,
            ExecutionStatus.ACTIVE,
        )


class BudgetTests(
    BaseExecutionTest
):

    def test_budget_transfer(self):
        self.activate()

        self.service.transfer_budget(
            tenant_id="tenant",
            project_id="project-1",
            from_cost_code="03-100",
            to_cost_code="26-100",
            amount_cents=1_000_000,
            actor_id="president",
        )

        project = self.service.project(
            tenant_id="tenant",
            project_id="project-1",
        )

        self.assertEqual(
            project.budget_lines[
                "03-100"
            ].current_budget_cents,
            39_000_000,
        )

        self.assertEqual(
            project.budget_lines[
                "26-100"
            ].current_budget_cents,
            26_000_000,
        )

    def test_budget_transfer_idempotent(self):
        self.activate()

        for _ in range(2):
            self.service.transfer_budget(
                tenant_id="tenant",
                project_id="project-1",
                from_cost_code="03-100",
                to_cost_code="26-100",
                amount_cents=1_000_000,
                actor_id="president",
                idempotency_key="transfer-1",
            )

        project = self.service.project(
            tenant_id="tenant",
            project_id="project-1",
        )

        self.assertEqual(
            project.budget_lines[
                "03-100"
            ].current_budget_cents,
            39_000_000,
        )

    def test_idempotency_conflict(self):
        self.activate()

        self.service.transfer_budget(
            tenant_id="tenant",
            project_id="project-1",
            from_cost_code="03-100",
            to_cost_code="26-100",
            amount_cents=1_000_000,
            actor_id="president",
            idempotency_key="same",
        )

        with self.assertRaises(
            DuplicateMutationConflict
        ):
            self.service.transfer_budget(
                tenant_id="tenant",
                project_id="project-1",
                from_cost_code="03-100",
                to_cost_code="26-100",
                amount_cents=2_000_000,
                actor_id="president",
                idempotency_key="same",
            )


class CommitmentTests(
    BaseExecutionTest
):

    def test_commitment_lifecycle(self):
        self.activate()

        commitment = (
            self.service
            .create_commitment(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="26-100",
                commitment_type=(
                    CommitmentType
                    .SUBCONTRACT
                ),
                vendor_name="Electrical Co",
                description="Electrical scope",
                amount_cents=20_000_000,
                actor_id="pm",
            )
        )

        self.assertEqual(
            commitment.status,
            CommitmentStatus.DRAFT,
        )

        approved = (
            self.service
            .approve_commitment(
                tenant_id="tenant",
                project_id="project-1",
                commitment_id=(
                    commitment
                    .commitment_id
                ),
                actor_id="president",
            )
        )

        self.assertEqual(
            approved.status,
            CommitmentStatus.APPROVED,
        )

    def test_commitment_change(self):
        self.activate()

        commitment = (
            self.service
            .create_commitment(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="26-100",
                commitment_type=(
                    CommitmentType
                    .PURCHASE_ORDER
                ),
                vendor_name="Vendor",
                description="Gear",
                amount_cents=5_000_000,
                actor_id="pm",
            )
        )

        self.service.approve_commitment(
            tenant_id="tenant",
            project_id="project-1",
            commitment_id=(
                commitment.commitment_id
            ),
            actor_id="president",
        )

        changed = (
            self.service
            .add_commitment_change(
                tenant_id="tenant",
                project_id="project-1",
                commitment_id=(
                    commitment.commitment_id
                ),
                amount_cents=500_000,
                actor_id="president",
                reason="Added scope",
            )
        )

        self.assertEqual(
            changed.current_amount_cents,
            5_500_000,
        )

    def test_commitment_idempotency(self):
        self.activate()

        first = (
            self.service
            .create_commitment(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="22-100",
                commitment_type=(
                    CommitmentType
                    .SUBCONTRACT
                ),
                vendor_name="Plumber",
                description="Plumbing",
                amount_cents=10_000_000,
                actor_id="pm",
                idempotency_key="po-1",
            )
        )

        second = (
            self.service
            .create_commitment(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="22-100",
                commitment_type=(
                    CommitmentType
                    .SUBCONTRACT
                ),
                vendor_name="Plumber",
                description="Plumbing",
                amount_cents=10_000_000,
                actor_id="pm",
                idempotency_key="po-1",
            )
        )

        self.assertEqual(
            first.commitment_id,
            second.commitment_id,
        )


class ActualCostTests(
    BaseExecutionTest
):

    def test_actual_cost(self):
        self.activate()

        actual = (
            self.service
            .record_actual_cost(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="03-100",
                category=(
                    CostCategory.MATERIAL
                ),
                amount_cents=2_000_000,
                incurred_on=(
                    date(
                        2026,
                        8,
                        15,
                    )
                ),
                description="Concrete",
                source_reference="invoice-1",
                actor_id="accounting",
            )
        )

        self.assertEqual(
            actual.amount_cents,
            2_000_000,
        )

    def test_actual_against_commitment(self):
        self.activate()

        commitment = (
            self.service
            .create_commitment(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="26-100",
                commitment_type=(
                    CommitmentType
                    .SUBCONTRACT
                ),
                vendor_name="Electrical",
                description="Electrical",
                amount_cents=20_000_000,
                actor_id="pm",
            )
        )

        self.service.approve_commitment(
            tenant_id="tenant",
            project_id="project-1",
            commitment_id=(
                commitment.commitment_id
            ),
            actor_id="president",
        )

        self.service.record_actual_cost(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="26-100",
            category=(
                CostCategory.SUBCONTRACT
            ),
            amount_cents=3_000_000,
            incurred_on=date(
                2026,
                8,
                15,
            ),
            description="Pay app",
            source_reference="payapp-1",
            actor_id="accounting",
            commitment_id=(
                commitment.commitment_id
            ),
        )

        self.assertEqual(
            commitment.invoiced_cents,
            3_000_000,
        )

        self.assertEqual(
            commitment.remaining_cents,
            17_000_000,
        )


class FieldProductionTests(
    BaseExecutionTest
):

    def test_progress(self):
        self.activate()

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            percent_complete=0.25,
            actor_id="pm",
        )

        forecast = (
            self.service.forecast(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        concrete = next(
            item
            for item
            in forecast.cost_codes
            if item.cost_code
            == "03-100"
        )

        self.assertEqual(
            concrete.percent_complete,
            0.25,
        )

    def test_progress_cannot_reverse(self):
        self.activate()

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                10,
            ),
            percent_complete=0.50,
            actor_id="pm",
        )

        with self.assertRaises(
            Exception
        ):
            self.service.set_progress(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="03-100",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
                percent_complete=0.40,
                actor_id="pm",
            )

    def test_daily_log(self):
        self.activate()

        log = (
            self.service
            .record_daily_log(
                tenant_id="tenant",
                project_id="project-1",
                work_date=date(
                    2026,
                    8,
                    15,
                ),
                submitted_by="foreman",
                labor_hours=80,
                equipment_hours=10,
                production=(
                    QuantityProduction(
                        cost_code="03-100",
                        description="Slab",
                        quantity=1000,
                        unit="SF",
                        labor_hours=80,
                        planned_labor_hours_per_unit=(
                            0.05
                        ),
                    ),
                ),
                constraints=(),
                safety_notes=(),
                weather_summary="Clear",
                actor_id="foreman",
            )
        )

        self.assertEqual(
            log.labor_hours,
            80,
        )

    def test_productivity(self):
        self.activate()

        self.service.record_daily_log(
            tenant_id="tenant",
            project_id="project-1",
            work_date=date(
                2026,
                8,
                15,
            ),
            submitted_by="foreman",
            labor_hours=100,
            equipment_hours=0,
            production=(
                QuantityProduction(
                    cost_code="03-100",
                    description="Wall",
                    quantity=100,
                    unit="LF",
                    labor_hours=100,
                    planned_labor_hours_per_unit=(
                        0.8
                    ),
                ),
            ),
            actor_id="foreman",
        )

        productivity = (
            self.service
            .productivity(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="03-100",
            )
        )

        self.assertAlmostEqual(
            productivity
            .efficiency_ratio,
            0.8,
        )


class MaterialTests(
    BaseExecutionTest
):

    def test_material_lifecycle(self):
        self.activate()

        release = (
            self.service
            .create_material_release(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="03-100",
                description="Rebar",
                quantity=20,
                unit="TON",
                required_on_site=date(
                    2026,
                    9,
                    1,
                ),
                committed_cents=1_000_000,
                actor_id="pm",
            )
        )

        ordered = (
            self.service
            .mark_material_ordered(
                tenant_id="tenant",
                project_id="project-1",
                release_id=(
                    release.release_id
                ),
                ordered_on=date(
                    2026,
                    8,
                    15,
                ),
                vendor_name="Steel Vendor",
                actor_id="pm",
            )
        )

        self.assertEqual(
            ordered.status,
            MaterialReleaseStatus
            .ORDERED,
        )

        partial = (
            self.service
            .mark_material_delivered(
                tenant_id="tenant",
                project_id="project-1",
                release_id=(
                    release.release_id
                ),
                delivered_on=date(
                    2026,
                    8,
                    20,
                ),
                delivered_quantity=10,
                actor_id="pm",
            )
        )

        self.assertEqual(
            partial.status,
            MaterialReleaseStatus
            .PARTIAL,
        )

        complete = (
            self.service
            .mark_material_delivered(
                tenant_id="tenant",
                project_id="project-1",
                release_id=(
                    release.release_id
                ),
                delivered_on=date(
                    2026,
                    8,
                    25,
                ),
                delivered_quantity=10,
                actor_id="pm",
            )
        )

        self.assertEqual(
            complete.status,
            MaterialReleaseStatus
            .DELIVERED,
        )


class ChangeEventTests(
    BaseExecutionTest
):

    def test_change_approval_updates_contract_and_budget(self):
        self.activate()

        change = (
            self.service
            .create_change_event(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="03-100",
                description="Added wall",
                estimated_cost_exposure_cents=(
                    1_000_000
                ),
                requested_price_cents=(
                    1_500_000
                ),
                actor_id="pm",
            )
        )

        self.service.set_change_status(
            tenant_id="tenant",
            project_id="project-1",
            change_id=(
                change.change_id
            ),
            status=(
                ChangeEventStatus
                .SUBMITTED
            ),
            actor_id="pm",
        )

        self.service.approve_change(
            tenant_id="tenant",
            project_id="project-1",
            change_id=(
                change.change_id
            ),
            approved_cost_cents=(
                900_000
            ),
            approved_price_cents=(
                1_400_000
            ),
            actor_id="president",
        )

        forecast = (
            self.service.forecast(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        self.assertEqual(
            forecast
            .current_contract_value_cents,
            101_400_000,
        )

        concrete = next(
            item
            for item
            in forecast.cost_codes
            if item.cost_code
            == "03-100"
        )

        self.assertEqual(
            concrete.budget_cents,
            40_900_000,
        )

    def test_unapproved_change_exposure(self):
        self.activate()

        self.service.create_change_event(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            description="Unknown condition",
            estimated_cost_exposure_cents=(
                3_000_000
            ),
            requested_price_cents=(
                4_000_000
            ),
            actor_id="pm",
            executed_at_risk=True,
        )

        forecast = (
            self.service.forecast(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        self.assertEqual(
            forecast
            .unresolved_change_exposure_cents,
            3_000_000,
        )

        self.assertEqual(
            forecast
            .at_risk_change_exposure_cents,
            3_000_000,
        )


class BillingTests(
    BaseExecutionTest
):

    def test_billing_cash_wip(self):
        self.activate()

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            percent_complete=0.50,
            actor_id="pm",
        )

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="26-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            percent_complete=0.50,
            actor_id="pm",
        )

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="22-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            percent_complete=0.50,
            actor_id="pm",
        )

        self.service.record_billing(
            tenant_id="tenant",
            project_id="project-1",
            period_end=date(
                2026,
                8,
                15,
            ),
            gross_billed_cents=(
                40_000_000
            ),
            retainage_held_cents=(
                4_000_000
            ),
            collected_cents=(
                30_000_000
            ),
            actor_id="accounting",
        )

        forecast = (
            self.service.forecast(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        self.assertEqual(
            forecast
            .accounts_receivable_cents,
            10_000_000,
        )

        self.assertGreater(
            forecast
            .earned_revenue_cents,
            0,
        )


class ForecastTests(
    BaseExecutionTest
):

    def test_performance_forecast(self):
        self.activate()

        self.service.record_actual_cost(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            category=(
                CostCategory.LABOR
            ),
            amount_cents=(
                15_000_000
            ),
            incurred_on=date(
                2026,
                8,
                15,
            ),
            description="Concrete costs",
            source_reference="cost",
            actor_id="accounting",
        )

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            percent_complete=0.25,
            actor_id="pm",
        )

        forecast = (
            self.service.forecast(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        concrete = next(
            item
            for item
            in forecast.cost_codes
            if item.cost_code
            == "03-100"
        )

        self.assertEqual(
            concrete
            .estimate_at_completion_cents,
            60_000_000,
        )

        self.assertLess(
            concrete.cpi,
            1.0,
        )

    def test_manual_etc_override(self):
        self.activate()

        self.service.record_actual_cost(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            category=(
                CostCategory.LABOR
            ),
            amount_cents=(
                10_000_000
            ),
            incurred_on=date(
                2026,
                8,
                15,
            ),
            description="Cost",
            source_reference="cost",
            actor_id="accounting",
        )

        self.service.set_manual_etc(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            etc_cents=20_000_000,
            actor_id="president",
            reason="Executive forecast",
        )

        forecast = (
            self.service.forecast(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        concrete = next(
            item
            for item
            in forecast.cost_codes
            if item.cost_code
            == "03-100"
        )

        self.assertEqual(
            concrete
            .estimate_at_completion_cents,
            30_000_000,
        )

    def test_spi(self):
        self.activate()

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            percent_complete=0.25,
            actor_id="pm",
        )

        self.service.set_planned_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            planned_percent_complete=0.50,
            actor_id="scheduler",
        )

        forecast = (
            self.service.forecast(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        concrete = next(
            item
            for item
            in forecast.cost_codes
            if item.cost_code
            == "03-100"
        )

        self.assertAlmostEqual(
            concrete.spi,
            0.5,
        )


class ExecutiveInterventionTests(
    BaseExecutionTest
):

    def test_margin_erosion_alert(self):
        self.activate()

        self.service.record_actual_cost(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            category=(
                CostCategory.LABOR
            ),
            amount_cents=(
                25_000_000
            ),
            incurred_on=date(
                2026,
                8,
                15,
            ),
            description="High cost",
            source_reference="cost",
            actor_id="accounting",
        )

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            percent_complete=0.25,
            actor_id="pm",
        )

        health = (
            self.service
            .executive_health(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        codes = {
            item.code
            for item
            in health.interventions
        }

        self.assertIn(
            "MARGIN_EROSION",
            codes,
        )

        self.assertIn(
            "LOW_CPI",
            codes,
        )

    def test_at_risk_change_alert(self):
        self.activate()

        self.service.create_change_event(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            description="Changed scope",
            estimated_cost_exposure_cents=(
                2_500_000
            ),
            requested_price_cents=(
                3_500_000
            ),
            executed_at_risk=True,
            actor_id="pm",
        )

        health = (
            self.service
            .executive_health(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        codes = {
            item.code
            for item
            in health.interventions
        }

        self.assertIn(
            "AT_RISK_CHANGE_WORK",
            codes,
        )

    def test_late_material_alert(self):
        self.activate()

        self.service.create_material_release(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="26-100",
            description="Switchgear",
            quantity=1,
            unit="EA",
            required_on_site=date(
                2026,
                8,
                1,
            ),
            committed_cents=(
                5_000_000
            ),
            actor_id="pm",
        )

        health = (
            self.service
            .executive_health(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        codes = {
            item.code
            for item
            in health.interventions
        }

        self.assertIn(
            "LATE_MATERIAL",
            codes,
        )

    def test_low_productivity_alert(self):
        self.activate()

        self.service.record_daily_log(
            tenant_id="tenant",
            project_id="project-1",
            work_date=date(
                2026,
                8,
                15,
            ),
            submitted_by="foreman",
            labor_hours=100,
            equipment_hours=0,
            production=(
                QuantityProduction(
                    cost_code="03-100",
                    description="Walls",
                    quantity=100,
                    unit="LF",
                    labor_hours=100,
                    planned_labor_hours_per_unit=(
                        0.50
                    ),
                ),
            ),
            actor_id="foreman",
        )

        health = (
            self.service
            .executive_health(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        codes = {
            item.code
            for item
            in health.interventions
        }

        self.assertIn(
            "LOW_FIELD_PRODUCTIVITY",
            codes,
        )


class AuditTests(
    BaseExecutionTest
):

    def test_chain_survives_multiple_operations(self):
        self.activate()

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            percent_complete=0.1,
            actor_id="pm",
        )

        self.assertTrue(
            self.service
            .verify_audit_chain(
                tenant_id="tenant",
                project_id="project-1",
            )
        )

    def test_payload_tamper_detected(self):
        self.activate()

        project = self.service.project(
            tenant_id="tenant",
            project_id="project-1",
        )

        event = project.audit[0]

        project.audit[0] = replace(
            event,
            payload={
                "tampered":
                    True
            },
        )

        with self.assertRaises(
            AuditIntegrityError
        ):
            self.service.verify_audit_chain(
                tenant_id="tenant",
                project_id="project-1",
            )


class DurableBridgeTests(
    BaseExecutionTest
):

    def test_publish_to_durable_store(self):
        with (
            tempfile
            .TemporaryDirectory()
        ) as temp:
            store = DurableStore(
                Path(temp)
                / "data.db"
            )

            try:
                bridge = (
                    ExecutionPersistenceBridge(
                        store=store
                    )
                )

                event = (
                    self.project
                    .audit[0]
                )

                result = bridge.publish(
                    tenant_id="tenant",
                    project_id="project-1",
                    audit_event=event,
                )

                self.assertEqual(
                    result.stream_version,
                    1,
                )

                events = (
                    store.read_stream(
                        tenant_id="tenant",
                        stream_id=(
                            "execution:"
                            "project-1"
                        ),
                    )
                )

                self.assertEqual(
                    len(events),
                    1,
                )

                self.assertEqual(
                    store
                    .health()
                    .pending_outbox_count,
                    1,
                )

            finally:
                store.close()


class IntegratedProjectScenarioTests(
    BaseExecutionTest
):

    def test_full_award_to_forecast_scenario(self):
        self.activate()

        commitment = (
            self.service
            .create_commitment(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="26-100",
                commitment_type=(
                    CommitmentType
                    .SUBCONTRACT
                ),
                vendor_name="Electrical",
                description="Electrical scope",
                amount_cents=20_000_000,
                actor_id="pm",
            )
        )

        self.service.approve_commitment(
            tenant_id="tenant",
            project_id="project-1",
            commitment_id=(
                commitment.commitment_id
            ),
            actor_id="president",
        )

        self.service.record_actual_cost(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            category=(
                CostCategory.LABOR
            ),
            amount_cents=8_000_000,
            incurred_on=date(
                2026,
                8,
                15,
            ),
            description="Concrete production",
            source_reference="job-cost",
            actor_id="accounting",
        )

        self.service.set_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            percent_complete=0.25,
            actor_id="pm",
        )

        self.service.set_planned_progress(
            tenant_id="tenant",
            project_id="project-1",
            cost_code="03-100",
            as_of=date(
                2026,
                8,
                15,
            ),
            planned_percent_complete=0.30,
            actor_id="scheduler",
        )

        self.service.record_daily_log(
            tenant_id="tenant",
            project_id="project-1",
            work_date=date(
                2026,
                8,
                15,
            ),
            submitted_by="foreman",
            labor_hours=80,
            equipment_hours=10,
            production=(
                QuantityProduction(
                    cost_code="03-100",
                    description="Concrete",
                    quantity=1000,
                    unit="SF",
                    labor_hours=80,
                    planned_labor_hours_per_unit=(
                        0.07
                    ),
                ),
            ),
            actor_id="foreman",
        )

        change = (
            self.service
            .create_change_event(
                tenant_id="tenant",
                project_id="project-1",
                cost_code="03-100",
                description="Owner change",
                estimated_cost_exposure_cents=(
                    1_000_000
                ),
                requested_price_cents=(
                    1_500_000
                ),
                actor_id="pm",
            )
        )

        self.service.set_change_status(
            tenant_id="tenant",
            project_id="project-1",
            change_id=(
                change.change_id
            ),
            status=(
                ChangeEventStatus
                .SUBMITTED
            ),
            actor_id="pm",
        )

        self.service.approve_change(
            tenant_id="tenant",
            project_id="project-1",
            change_id=(
                change.change_id
            ),
            approved_cost_cents=(
                900_000
            ),
            approved_price_cents=(
                1_400_000
            ),
            actor_id="president",
        )

        self.service.record_billing(
            tenant_id="tenant",
            project_id="project-1",
            period_end=date(
                2026,
                8,
                15,
            ),
            gross_billed_cents=(
                10_000_000
            ),
            retainage_held_cents=(
                1_000_000
            ),
            collected_cents=(
                8_000_000
            ),
            actor_id="accounting",
        )

        forecast = (
            self.service.forecast(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        health = (
            self.service
            .executive_health(
                tenant_id="tenant",
                project_id="project-1",
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        self.assertGreater(
            forecast
            .current_contract_value_cents,
            100_000_000,
        )

        self.assertGreater(
            forecast
            .estimate_at_completion_cents,
            0,
        )

        self.assertGreaterEqual(
            health.score,
            0,
        )

        self.assertLessEqual(
            health.score,
            100,
        )

        self.assertTrue(
            self.service
            .verify_audit_chain(
                tenant_id="tenant",
                project_id="project-1",
            )
        )


if __name__ == "__main__":
    unittest.main()
