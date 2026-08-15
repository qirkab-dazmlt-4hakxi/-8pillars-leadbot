import unittest

from datetime import (
    date,
    datetime,
    timezone,
)

from leadbot_v2.goat.execution import (
    AwardBudgetLine,
    AwardHandoff,
    AwardToExecutionService,
    CostCategory,
)

from leadbot_v2.goat.field_ops import (
    ComplianceStatus,
    CrewRole,
    FieldOperationsService,
    FieldRiskSeverity,
    HazardControl,
    InspectionItem,
    InspectionResult,
    MobileMutation,
    PayAppStatus,
    RFIStatus,
    SafetySeverity,
    SubmittalStatus,
    SyncMutationType,
    TimecardStatus,
    WaiverType,
)


UTC = timezone.utc


class FieldBase(
    unittest.TestCase
):
    def setUp(self):
        self.service = (
            FieldOperationsService()
        )

        self.worker = (
            self.service.create_worker(
                employee_number="E001",
                name="Foreman",
                role=CrewRole.FOREMAN,
                base_rate_cents_per_hour=5000,
                payroll_burden_bps=1000,
                benefits_bps=500,
                workers_comp_bps=500,
                supervision_bps=250,
                actor_id="president",
            )
        )

        self.crew = (
            self.service.create_crew(
                name="Concrete Crew A",
                actor_id="president",
            )
        )

        self.service.add_worker_to_crew(
            crew_id=self.crew.crew_id,
            worker_id=self.worker.worker_id,
            as_foreman=True,
            actor_id="president",
        )

    def make_execution(self):
        execution = (
            AwardToExecutionService()
        )

        execution.create_from_award(
            handoff=AwardHandoff(
                tenant_id="tenant",
                project_id="project-1",
                estimate_id="est-1",
                proposal_hash="hash",
                project_name="Project",
                original_contract_value_cents=100_000_000,
                budget_lines=(
                    AwardBudgetLine(
                        cost_code="03-100",
                        name="Concrete",
                        category=CostCategory.LABOR,
                        budget_cents=40_000_000,
                    ),
                ),
                awarded_at=datetime(
                    2026,
                    8,
                    15,
                    tzinfo=UTC,
                ),
            ),
            actor_id="president",
        )

        execution.activate(
            tenant_id="tenant",
            project_id="project-1",
            actor_id="president",
        )

        return execution


class WorkforceTests(FieldBase):
    def test_burdened_rate(self):
        self.assertGreater(
            self.worker
            .burdened_rate_cents_per_hour,
            self.worker
            .base_rate_cents_per_hour,
        )

    def test_crew_assignment(self):
        assignment = (
            self.service.assign_crew(
                crew_id=self.crew.crew_id,
                project_id="project-1",
                cost_code="03-100",
                start_date=date(
                    2026,
                    8,
                    15,
                ),
                actor_id="pm",
            )
        )

        self.assertEqual(
            assignment.project_id,
            "project-1",
        )


class TimecardTests(FieldBase):
    def create_card(self):
        return self.service.create_timecard(
            worker_id=self.worker.worker_id,
            project_id="project-1",
            cost_code="03-100",
            work_date=date(
                2026,
                8,
                15,
            ),
            regular_hours=8,
            overtime_hours=2,
            doubletime_hours=0,
            submitted_by="foreman",
            actor_id="foreman",
        )

    def test_timecard_lifecycle(self):
        card = self.create_card()

        self.assertEqual(
            card.status,
            TimecardStatus.DRAFT,
        )

        self.service.submit_timecard(
            timecard_id=card.timecard_id,
            actor_id="foreman",
        )

        self.service.approve_timecard(
            timecard_id=card.timecard_id,
            approved_by="pm",
            actor_id="pm",
        )

        self.assertEqual(
            card.status,
            TimecardStatus.APPROVED,
        )

    def test_labor_cost(self):
        card = self.create_card()

        result = self.service.labor_cost(
            timecard_id=card.timecard_id
        )

        self.assertGreater(
            result.total_cost_cents,
            0,
        )

    def test_timecard_posts_to_execution(self):
        execution = (
            self.make_execution()
        )

        card = self.create_card()

        self.service.submit_timecard(
            timecard_id=card.timecard_id,
            actor_id="foreman",
        )

        self.service.approve_timecard(
            timecard_id=card.timecard_id,
            approved_by="pm",
            actor_id="pm",
        )

        result = (
            self.service
            .post_approved_timecard_to_execution(
                timecard_id=card.timecard_id,
                execution_service=execution,
                tenant_id="tenant",
                actor_id="accounting",
            )
        )

        self.assertGreater(
            result.amount_cents,
            0,
        )

        self.assertEqual(
            card.status,
            TimecardStatus.POSTED,
        )


class EquipmentTests(FieldBase):
    def test_equipment_cost_bridge(self):
        execution = (
            self.make_execution()
        )

        equipment = (
            self.service.create_equipment(
                name="Excavator",
                asset_number="EX-001",
                hourly_cost_cents=15000,
                actor_id="fleet",
            )
        )

        usage = (
            self.service
            .record_equipment_usage(
                equipment_id=(
                    equipment.equipment_id
                ),
                project_id="project-1",
                cost_code="03-100",
                work_date=date(
                    2026,
                    8,
                    15,
                ),
                hours=4,
                actor_id="foreman",
            )
        )

        actual = (
            self.service
            .post_equipment_usage_to_execution(
                usage_id=usage.usage_id,
                execution_service=execution,
                tenant_id="tenant",
                actor_id="accounting",
            )
        )

        self.assertEqual(
            actual.amount_cents,
            60000,
        )


class QualityTests(FieldBase):
    def test_failed_inspection_requires_action(self):
        with self.assertRaises(
            Exception
        ):
            self.service.create_inspection(
                project_id="project-1",
                cost_code="03-100",
                inspection_type="Pre-pour",
                performed_on=date(
                    2026,
                    8,
                    15,
                ),
                performed_by="QC",
                result=InspectionResult.FAIL,
                items=(),
                actor_id="QC",
            )

    def test_quality_lifecycle(self):
        inspection = (
            self.service.create_inspection(
                project_id="project-1",
                cost_code="03-100",
                inspection_type="Pre-pour",
                performed_on=date(
                    2026,
                    8,
                    15,
                ),
                performed_by="QC",
                result=InspectionResult.FAIL,
                items=(
                    InspectionItem(
                        item_id="I1",
                        description="Rebar spacing",
                        result=(
                            InspectionResult.FAIL
                        ),
                    ),
                ),
                corrective_action=(
                    "Correct and reinspect"
                ),
                actor_id="QC",
            )
        )

        self.service.close_inspection(
            inspection_id=(
                inspection.inspection_id
            ),
            actor_id="QC",
        )

        self.assertTrue(
            inspection.closed
        )


class SafetyTests(FieldBase):
    def test_jsa(self):
        jsa = self.service.create_jsa(
            project_id="project-1",
            work_date=date(
                2026,
                8,
                15,
            ),
            activity="Concrete placement",
            prepared_by="foreman",
            crew_id=self.crew.crew_id,
            hazards=(
                HazardControl(
                    hazard="Vehicle interaction",
                    control=(
                        "Project-specific traffic control"
                    ),
                    severity=(
                        SafetySeverity.HIGH
                    ),
                ),
            ),
            attendee_worker_ids=(
                self.worker.worker_id,
            ),
            actor_id="foreman",
        )

        self.service.acknowledge_jsa(
            jsa_id=jsa.jsa_id,
            actor_id="foreman",
        )

        self.assertTrue(
            jsa.acknowledged
        )


class RFITests(FieldBase):
    def test_rfi_lifecycle(self):
        rfi = self.service.create_rfi(
            project_id="project-1",
            subject="Beam detail",
            question=(
                "Clarify conflicting beam depth."
            ),
            created_by="pm",
            due_date=date(
                2026,
                8,
                20,
            ),
            drawing_refs=("S3.1",),
            actor_id="pm",
        )

        self.assertEqual(
            rfi.status,
            RFIStatus.OPEN,
        )

        self.service.answer_rfi(
            rfi_id=rfi.rfi_id,
            answer="Use detail 4/S5.2.",
            answered_by="EOR",
            actor_id="pm",
        )

        self.assertEqual(
            rfi.status,
            RFIStatus.ANSWERED,
        )


class SubmittalTests(FieldBase):
    def test_submittal_cycle(self):
        submittal = (
            self.service.create_submittal(
                project_id="project-1",
                title="Concrete mix design",
                spec_section="03 30 00",
                required_on_site=date(
                    2026,
                    9,
                    1,
                ),
                actor_id="pm",
            )
        )

        self.service.submit_submittal(
            submittal_id=(
                submittal.submittal_id
            ),
            submitted_on=date(
                2026,
                8,
                15,
            ),
            actor_id="pm",
        )

        self.service.review_submittal(
            submittal_id=(
                submittal.submittal_id
            ),
            status=(
                SubmittalStatus
                .APPROVED_AS_NOTED
            ),
            returned_on=date(
                2026,
                8,
                18,
            ),
            review_notes="Approved",
            actor_id="pm",
        )

        self.assertEqual(
            submittal.status,
            SubmittalStatus
            .APPROVED_AS_NOTED,
        )


class PunchTests(FieldBase):
    def test_punch(self):
        item = (
            self.service.create_punch_item(
                project_id="project-1",
                location="Level 1",
                description="Patch edge",
                created_by="QC",
                actor_id="QC",
            )
        )

        self.service.close_punch_item(
            punch_id=item.punch_id,
            actor_id="QC",
        )

        self.assertEqual(
            item.status.value,
            "closed",
        )


class ComplianceTests(FieldBase):
    def compliant_sub(self):
        sub = (
            self.service
            .create_subcontractor(
                company_name="Sub Co",
                actor_id="pm",
            )
        )

        for document_type in (
            "insurance",
            "w9",
            "agreement",
            "safety",
        ):
            self.service.upsert_compliance_document(
                subcontractor_id=(
                    sub.subcontractor_id
                ),
                document_type=(
                    document_type
                ),
                status=(
                    ComplianceStatus.COMPLIANT
                ),
                expires_on=date(
                    2027,
                    1,
                    1,
                ),
                actor_id="pm",
            )

        return sub

    def test_compliance(self):
        sub = self.compliant_sub()

        state = (
            self.service
            .compliance_state(
                subcontractor_id=(
                    sub.subcontractor_id
                ),
                as_of=date(
                    2026,
                    8,
                    15,
                ),
            )
        )

        self.assertEqual(
            state,
            ComplianceStatus.COMPLIANT,
        )

    def test_pay_app_compliance_gate(self):
        sub = self.compliant_sub()

        waiver = (
            self.service.create_waiver(
                subcontractor_id=(
                    sub.subcontractor_id
                ),
                project_id="project-1",
                waiver_type=(
                    WaiverType
                    .CONDITIONAL_PROGRESS
                ),
                through_date=date(
                    2026,
                    8,
                    15,
                ),
                amount_cents=1_000_000,
                signed=True,
                actor_id="accounting",
            )
        )

        pay_app = (
            self.service.create_pay_app(
                subcontractor_id=(
                    sub.subcontractor_id
                ),
                project_id="project-1",
                cost_code="03-100",
                period_end=date(
                    2026,
                    8,
                    15,
                ),
                gross_amount_cents=1_000_000,
                retainage_cents=100_000,
                waiver_id=(
                    waiver.waiver_id
                ),
                actor_id="accounting",
            )
        )

        self.service.submit_pay_app(
            pay_app_id=(
                pay_app.pay_app_id
            ),
            as_of=date(
                2026,
                8,
                15,
            ),
            actor_id="accounting",
        )

        self.service.approve_pay_app(
            pay_app_id=(
                pay_app.pay_app_id
            ),
            approved_amount_cents=900_000,
            actor_id="president",
        )

        self.assertEqual(
            pay_app.status,
            PayAppStatus.APPROVED,
        )


class MobileSyncTests(FieldBase):
    def test_mobile_sync(self):
        mutation = MobileMutation(
            mutation_id="m1",
            device_id="ipad-field-1",
            entity_type="daily_note",
            entity_id="N1",
            mutation_type=(
                SyncMutationType.CREATE
            ),
            base_version=0,
            payload={
                "note":
                    "Field note"
            },
            client_created_at=datetime(
                2026,
                8,
                15,
                12,
                tzinfo=UTC,
            ),
        )

        result = (
            self.service
            .apply_mobile_mutation(
                mutation=mutation,
                actor_id="foreman",
            )
        )

        self.assertTrue(
            result.accepted
        )

        stale = MobileMutation(
            mutation_id="m2",
            device_id="iphone-field-2",
            entity_type="daily_note",
            entity_id="N1",
            mutation_type=(
                SyncMutationType.UPDATE
            ),
            base_version=0,
            payload={
                "note":
                    "stale update"
            },
            client_created_at=datetime(
                2026,
                8,
                15,
                13,
                tzinfo=UTC,
            ),
        )

        conflict = (
            self.service
            .apply_mobile_mutation(
                mutation=stale,
                actor_id="foreman",
            )
        )

        self.assertTrue(
            conflict.conflict
        )


class CommandCenterTests(FieldBase):
    def test_risk_snapshot(self):
        self.service.create_rfi(
            project_id="project-1",
            subject="Late RFI",
            question="Need answer",
            created_by="pm",
            due_date=date(
                2026,
                8,
                1,
            ),
            actor_id="pm",
        )

        inspection = (
            self.service.create_inspection(
                project_id="project-1",
                cost_code="03-100",
                inspection_type="Pre-pour",
                performed_on=date(
                    2026,
                    8,
                    15,
                ),
                performed_by="QC",
                result=InspectionResult.HOLD,
                items=(),
                corrective_action="Correct",
                actor_id="QC",
            )
        )

        snapshot = (
            self.service
            .command_snapshot(
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
            in snapshot.risks
        }

        self.assertIn(
            "OVERDUE_RFI",
            codes,
        )

        self.assertIn(
            "OPEN_QAQC_FAILURE",
            codes,
        )

        self.assertLess(
            snapshot.health_score,
            100,
        )


class AuditTests(FieldBase):
    def test_audit_chain(self):
        self.service.assign_crew(
            crew_id=self.crew.crew_id,
            project_id="project-1",
            cost_code="03-100",
            start_date=date(
                2026,
                8,
                15,
            ),
            actor_id="pm",
        )

        self.assertTrue(
            self.service
            .verify_audit_chain()
        )


if __name__ == "__main__":
    unittest.main()
