import unittest

from dataclasses import replace

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
    CostCategory,
    ProjectFinanceService,
)
from leadbot_v2.goat.preconstruction.estimating.workflow import (
    EstimateAuthorizationError,
    EstimateStatus,
    EstimateWorkflowError,
    EstimateWorkflowService,
    RFIImpactStatus,
    calculate_version_hash,
)
from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
)
from leadbot_v2.goat.preconstruction.pricing.engine import (
    CostClass,
    PricedAssembly,
    PricingComponent,
    PricingUnit,
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


def priced_assembly(
    *,
    assembly_id="asm-1",
    direct=100_000_00,
    bid=140_000_00,
    review=False,
):
    component = PricingComponent(
        rate_code="TEST",
        description="Test Component",
        unit=PricingUnit.LS,
        cost_class=CostClass.MATERIAL,
        quantity=1.0,
        cents_per_unit=direct,
        extension_cents=direct,
        source="Twins Approved Rate",
    )

    return PricedAssembly(
        assembly_id=assembly_id,
        description="Structural Concrete",
        components=(component,),
        direct_cost_cents=direct,
        overhead_cents=0,
        contingency_cents=0,
        profit_cents=(
            bid - direct
        ),
        bid_price_cents=bid,
        provenance=GeometryProvenance(
            document_id="doc-1",
            sheet_number="S2.1",
            page_number=3,
            source_ref="plans.pdf#page=3",
            geometry_ids=(
                "geometry-1",
            ),
            text_refs=(
                "callout-1",
            ),
            confidence=0.98,
        ),
        confidence=0.98,
        requires_review=review,
    )


class EstimateWorkflowTests(
    unittest.TestCase
):

    def setUp(self):
        self.spine = InMemoryDataSpine()

        self.workflow = (
            EstimateWorkflowService(
                spine=self.spine
            )
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

        self.estimate = (
            self.workflow.create_estimate(
                tenant_id=TENANT,
                business_unit_id=BU,
                project_name=(
                    "Quantum Estimate Test"
                ),
                actor_id="estimator",
            )
        )

    def add_line(
        self,
        *,
        direct=100_000_00,
        bid=140_000_00,
        review=False,
        cost_code="03-3000",
    ):
        return (
            self.workflow
            .add_priced_assembly(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                actor_id="estimator",
                assembly=(
                    priced_assembly(
                        direct=direct,
                        bid=bid,
                        review=review,
                    )
                ),
                cost_code=cost_code,
            )
        )

    def approve_and_lock(self):
        self.add_line()

        self.workflow.approve(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        return self.workflow.lock(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

    def test_new_estimate_is_draft(self):
        self.assertEqual(
            self.estimate.status,
            EstimateStatus.DRAFT,
        )

    def test_new_estimate_hash_verifies(self):
        self.assertTrue(
            self.workflow.verify_integrity(
                self.estimate.version_id
            )
        )

    def test_manual_line_updates_totals(self):
        self.workflow.add_manual_line(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            description="Earthwork",
            cost_code="31-2000",
            quantity=100.0,
            unit="CY",
            direct_cost_cents=50_000_00,
            bid_price_cents=75_000_00,
        )

        current = (
            self.workflow.current_version(
                self.estimate.estimate_id
            )
        )

        self.assertEqual(
            current.base_direct_cost_cents,
            50_000_00,
        )

        self.assertEqual(
            current.base_bid_price_cents,
            75_000_00,
        )

    def test_priced_assembly_becomes_estimate_line(self):
        line = self.add_line()

        self.assertEqual(
            line.direct_cost_cents,
            100_000_00,
        )

        self.assertIn(
            "plans.pdf#page=3",
            line.source_refs,
        )

        self.assertIn(
            "geometry-1",
            line.source_refs,
        )

    def test_allowance_is_in_base_total(self):
        self.add_line(
            direct=100_00,
            bid=150_00,
        )

        self.workflow.add_allowance(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            description="Unknown utility",
            cost_code="31-2000",
            direct_cost_cents=50_00,
            bid_price_cents=75_00,
            reason="Existing utility unresolved",
        )

        current = (
            self.workflow.current_version(
                self.estimate.estimate_id
            )
        )

        self.assertEqual(
            current.base_direct_cost_cents,
            150_00,
        )

        self.assertEqual(
            current.base_bid_price_cents,
            225_00,
        )

    def test_alternate_not_in_base_total(self):
        self.add_line(
            direct=100_00,
            bid=150_00,
        )

        self.workflow.add_alternate(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            description="Add alternate",
            cost_code="03-3000",
            direct_cost_cents=50_00,
            bid_price_cents=80_00,
        )

        current = (
            self.workflow.current_version(
                self.estimate.estimate_id
            )
        )

        self.assertEqual(
            current.base_bid_price_cents,
            150_00,
        )

    def test_exclusion_is_preserved(self):
        exclusion = (
            self.workflow.add_exclusion(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                actor_id="estimator",
                description=(
                    "Rock excavation"
                ),
                reason=(
                    "Not shown in geotechnical data"
                ),
            )
        )

        current = (
            self.workflow.current_version(
                self.estimate.estimate_id
            )
        )

        self.assertIn(
            exclusion,
            current.exclusions,
        )

    def test_qualification_is_preserved(self):
        self.workflow.add_qualification(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            text=(
                "Pricing assumes normal weekday access."
            ),
        )

        current = (
            self.workflow.current_version(
                self.estimate.estimate_id
            )
        )

        self.assertEqual(
            len(current.qualifications),
            1,
        )

    def test_override_requires_reason(self):
        line = self.add_line()

        with self.assertRaises(
            ValueError
        ):
            self.workflow.override_line(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                actor_id="estimator",
                line_id=line.line_id,
                reason="",
                new_bid_price_cents=(
                    130_000_00
                ),
            )

    def test_override_changes_line_and_is_audited(self):
        line = self.add_line()

        override = (
            self.workflow.override_line(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                actor_id="senior-estimator",
                line_id=line.line_id,
                reason=(
                    "Negotiated ready-mix pricing"
                ),
                new_direct_cost_cents=(
                    90_000_00
                ),
                new_bid_price_cents=(
                    135_000_00
                ),
            )
        )

        current = (
            self.workflow.current_version(
                self.estimate.estimate_id
            )
        )

        self.assertEqual(
            current.lines[0]
            .direct_cost_cents,
            90_000_00,
        )

        self.assertEqual(
            len(current.overrides),
            1,
        )

        self.assertEqual(
            override.actor_id,
            "senior-estimator",
        )

    def test_blocking_rfi_prevents_approval(self):
        self.add_line()

        self.workflow.add_rfi_effect(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            rfi_id="RFI-001",
            description=(
                "Missing footing detail"
            ),
            cost_code="03-3000",
            cost_delta_cents=0,
            price_delta_cents=0,
            blocking=True,
        )

        with self.assertRaises(
            EstimateWorkflowError
        ):
            self.workflow.approve(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                principal=self.president,
            )

    def test_resolved_rfi_enters_estimate_total(self):
        self.add_line(
            direct=100_00,
            bid=150_00,
        )

        self.workflow.add_rfi_effect(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            rfi_id="RFI-002",
            description="Added concrete",
            cost_code="03-3000",
            cost_delta_cents=25_00,
            price_delta_cents=40_00,
            blocking=True,
        )

        effect = (
            self.workflow
            .resolve_rfi_effect(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                actor_id="estimator",
                rfi_id="RFI-002",
                resolution_note=(
                    "Engineer issued detail"
                ),
            )
        )

        current = (
            self.workflow.current_version(
                self.estimate.estimate_id
            )
        )

        self.assertEqual(
            effect.status,
            RFIImpactStatus.RESOLVED,
        )

        self.assertEqual(
            current.base_direct_cost_cents,
            125_00,
        )

        self.assertEqual(
            current.base_bid_price_cents,
            190_00,
        )

    def test_sales_cannot_approve_estimate(self):
        self.add_line()

        with self.assertRaises(
            EstimateAuthorizationError
        ):
            self.workflow.approve(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                principal=self.sales,
            )

    def test_president_can_approve(self):
        self.add_line()

        result = self.workflow.approve(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        self.assertEqual(
            result.status,
            EstimateStatus.APPROVED,
        )

    def test_review_line_blocks_approval(self):
        self.add_line(
            review=True,
        )

        with self.assertRaises(
            EstimateWorkflowError
        ):
            self.workflow.approve(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                principal=self.president,
            )

    def test_empty_estimate_cannot_be_approved(self):
        with self.assertRaises(
            EstimateWorkflowError
        ):
            self.workflow.approve(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                principal=self.president,
            )

    def test_draft_cannot_be_locked(self):
        self.add_line()

        with self.assertRaises(
            EstimateWorkflowError
        ):
            self.workflow.lock(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                principal=self.president,
            )

    def test_approved_estimate_can_be_locked(self):
        locked = self.approve_and_lock()

        self.assertEqual(
            locked.status,
            EstimateStatus.LOCKED,
        )

    def test_locked_estimate_rejects_edit(self):
        self.approve_and_lock()

        with self.assertRaises(
            EstimateWorkflowError
        ):
            self.workflow.add_exclusion(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                actor_id="estimator",
                description="Late exclusion",
                reason="test",
            )

    def test_submit_requires_locked_estimate(self):
        self.add_line()

        with self.assertRaises(
            EstimateWorkflowError
        ):
            self.workflow.submit(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                principal=self.president,
            )

    def test_locked_estimate_can_submit(self):
        self.approve_and_lock()

        submitted = self.workflow.submit(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        self.assertEqual(
            submitted.status,
            EstimateStatus.SUBMITTED,
        )

    def test_award_requires_submitted_estimate(self):
        self.approve_and_lock()

        with self.assertRaises(
            EstimateWorkflowError
        ):
            self.workflow.award(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                principal=self.president,
            )

    def test_unknown_award_alternate_rejected(self):
        self.approve_and_lock()

        self.workflow.submit(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        with self.assertRaises(
            EstimateWorkflowError
        ):
            self.workflow.award(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                principal=self.president,
                accepted_alternate_ids=(
                    "not-real",
                ),
            )

    def test_award_can_include_alternate(self):
        self.add_line(
            direct=100_00,
            bid=150_00,
        )

        alternate = (
            self.workflow.add_alternate(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                actor_id="estimator",
                description="Alternate",
                cost_code="03-3000",
                direct_cost_cents=50_00,
                bid_price_cents=75_00,
            )
        )

        self.workflow.approve(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        self.workflow.lock(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        self.workflow.submit(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        awarded = self.workflow.award(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
            accepted_alternate_ids=(
                alternate.alternate_id,
            ),
        )

        self.assertEqual(
            awarded.awarded_bid_price_cents,
            225_00,
        )

    def test_proposal_requires_locked_content(self):
        self.add_line()

        with self.assertRaises(
            EstimateWorkflowError
        ):
            self.workflow.proposal_snapshot(
                estimate_id=(
                    self.estimate
                    .estimate_id
                )
            )

    def test_proposal_contains_exclusions_and_hash(self):
        self.add_line()

        self.workflow.add_exclusion(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            description="Testing",
            reason="Not in scope",
        )

        self.workflow.approve(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        self.workflow.lock(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        proposal = (
            self.workflow
            .proposal_snapshot(
                estimate_id=(
                    self.estimate
                    .estimate_id
                )
            )
        )

        self.assertEqual(
            len(proposal.exclusions),
            1,
        )

        self.assertTrue(
            proposal.content_hash
        )

    def test_revision_increments_version(self):
        locked = self.approve_and_lock()

        revision = (
            self.workflow
            .create_revision(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                actor_id="estimator",
            )
        )

        self.assertEqual(
            revision.version_number,
            locked.version_number + 1,
        )

        self.assertEqual(
            revision.status,
            EstimateStatus.DRAFT,
        )

        self.assertEqual(
            revision.parent_version_id,
            locked.version_id,
        )

    def test_previous_version_remains_intact(self):
        locked = self.approve_and_lock()

        self.workflow.create_revision(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
        )

        old = self.workflow.get_version(
            locked.version_id
        )

        self.assertEqual(
            old.status,
            EstimateStatus.LOCKED,
        )

        self.assertTrue(
            self.workflow.verify_integrity(
                old.version_id
            )
        )

    def test_tampering_is_detected(self):
        self.add_line()

        current = (
            self.workflow.current_version(
                self.estimate.estimate_id
            )
        )

        self.workflow._versions[
            current.version_id
        ] = replace(
            current,
            project_name="TAMPERED",
        )

        self.assertFalse(
            self.workflow.verify_integrity(
                current.version_id
            )
        )

    def test_estimate_actions_write_data_spine_events(self):
        self.add_line()

        events = self.spine.events_for(
            tenant_id=TENANT,
            aggregate_id=(
                self.estimate.estimate_id
            ),
        )

        event_types = {
            item.event_type
            for item in events
        }

        self.assertIn(
            "estimate.created",
            event_types,
        )

        self.assertIn(
            "estimate.line.added",
            event_types,
        )


class EstimateBudgetHandoffTests(
    unittest.TestCase
):

    def setUp(self):
        self.spine = InMemoryDataSpine()

        self.crm = GoatCRM(
            self.spine
        )

        self.finance = (
            ProjectFinanceService(
                spine=self.spine
            )
        )

        self.workflow = (
            EstimateWorkflowService(
                spine=self.spine
            )
        )

        self.president = principal(
            "president",
            Role.PRESIDENT,
        )

        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="president",
            title="Awarded Project",
            source="GOAT",
        )

        opportunity = (
            self.crm.promote_lead(
                tenant_id=TENANT,
                actor_id="president",
                lead_id=lead.entity_id,
                estimated_value_cents=(
                    500_000_00
                ),
            )
        )

        won = (
            self.crm.set_opportunity_stage(
                tenant_id=TENANT,
                actor_id="president",
                opportunity_id=(
                    opportunity.entity_id
                ),
                stage=OpportunityStage.WON,
            )
        )

        self.project = (
            self.crm
            .create_project_from_won_opportunity(
                tenant_id=TENANT,
                actor_id="president",
                opportunity_id=(
                    won.entity_id
                ),
                contract_value_cents=(
                    500_000_00
                ),
            )
        )

        for code, name in (
            (
                "03-3000",
                "Concrete",
            ),
            (
                "31-2000",
                "Earthwork",
            ),
        ):
            self.finance.register_cost_code(
                principal=self.president,
                tenant_id=TENANT,
                business_unit_id=BU,
                code=code,
                name=name,
                category=(
                    CostCategory.MATERIAL
                ),
            )

        self.estimate = (
            self.workflow.create_estimate(
                tenant_id=TENANT,
                business_unit_id=BU,
                project_name=(
                    "Awarded Project"
                ),
                actor_id="estimator",
            )
        )

    def award_estimate(
        self,
        *,
        include_alt=False,
    ):
        self.workflow.add_manual_line(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            description="Concrete",
            cost_code="03-3000",
            quantity=1,
            unit="LS",
            direct_cost_cents=100_000_00,
            bid_price_cents=140_000_00,
        )

        self.workflow.add_allowance(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            description="Earthwork allowance",
            cost_code="31-2000",
            direct_cost_cents=25_000_00,
            bid_price_cents=35_000_00,
            reason="Unresolved quantity",
        )

        alternate = (
            self.workflow.add_alternate(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                actor_id="estimator",
                description="Concrete alternate",
                cost_code="03-3000",
                direct_cost_cents=10_000_00,
                bid_price_cents=15_000_00,
            )
        )

        self.workflow.approve(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        self.workflow.lock(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        self.workflow.submit(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
        )

        return self.workflow.award(
            estimate_id=(
                self.estimate.estimate_id
            ),
            principal=self.president,
            accepted_alternate_ids=(
                (
                    alternate.alternate_id,
                )
                if include_alt
                else ()
            ),
        )

    def test_unawarded_estimate_cannot_handoff(self):
        self.workflow.add_manual_line(
            estimate_id=(
                self.estimate.estimate_id
            ),
            actor_id="estimator",
            description="Concrete",
            cost_code="03-3000",
            quantity=1,
            unit="LS",
            direct_cost_cents=100_00,
            bid_price_cents=150_00,
        )

        with self.assertRaises(
            EstimateWorkflowError
        ):
            (
                self.workflow
                .handoff_to_project_budget(
                    estimate_id=(
                        self.estimate
                        .estimate_id
                    ),
                    project_id=(
                        self.project.entity_id
                    ),
                    principal=(
                        self.president
                    ),
                    finance=self.finance,
                )
            )

    def test_handoff_uses_direct_cost_not_bid_price(self):
        self.award_estimate()

        result = (
            self.workflow
            .handoff_to_project_budget(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                project_id=(
                    self.project.entity_id
                ),
                principal=self.president,
                finance=self.finance,
            )
        )

        self.assertEqual(
            result.total_budget_cents,
            125_000_00,
        )

    def test_accepted_alternate_enters_project_budget(self):
        self.award_estimate(
            include_alt=True,
        )

        result = (
            self.workflow
            .handoff_to_project_budget(
                estimate_id=(
                    self.estimate
                    .estimate_id
                ),
                project_id=(
                    self.project.entity_id
                ),
                principal=self.president,
                finance=self.finance,
            )
        )

        budget = dict(
            result.budget_by_cost_code
        )

        self.assertEqual(
            budget["03-3000"],
            110_000_00,
        )

        self.assertEqual(
            result.total_budget_cents,
            135_000_00,
        )

    def test_duplicate_budget_handoff_is_blocked(self):
        self.award_estimate()

        self.workflow.handoff_to_project_budget(
            estimate_id=(
                self.estimate.estimate_id
            ),
            project_id=(
                self.project.entity_id
            ),
            principal=self.president,
            finance=self.finance,
        )

        with self.assertRaises(
            EstimateWorkflowError
        ):
            (
                self.workflow
                .handoff_to_project_budget(
                    estimate_id=(
                        self.estimate
                        .estimate_id
                    ),
                    project_id=(
                        self.project
                        .entity_id
                    ),
                    principal=(
                        self.president
                    ),
                    finance=self.finance,
                )
            )


if __name__ == "__main__":
    unittest.main()
