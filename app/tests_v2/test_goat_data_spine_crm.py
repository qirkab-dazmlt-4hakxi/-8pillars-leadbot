import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from leadbot_v2.goat.crm.service import (
    CRMTransitionError,
    CRMValidationError,
    GoatCRM,
)
from leadbot_v2.goat.data_spine.models import (
    Lead,
    Opportunity,
    OpportunityStage,
    Project,
)
from leadbot_v2.goat.data_spine.store import (
    ConcurrencyConflict,
    InMemoryDataSpine,
    TenantIsolationError,
)
from leadbot_v2.goat.workflow.follow_through import (
    EscalationLevel,
    FollowThroughEngine,
    WorkStatus,
)


TENANT = "twins-development"
OTHER = "other-company"
BU = "twins-development"


def now() -> datetime:
    return datetime.now(timezone.utc)


class DataSpineTests(unittest.TestCase):

    def setUp(self):
        self.spine = InMemoryDataSpine()
        self.crm = GoatCRM(self.spine)

    def test_cross_tenant_access_is_denied(self):
        contact = self.crm.create_contact(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="president",
            display_name="GC Estimator",
        )

        with self.assertRaises(TenantIsolationError):
            self.spine.get(
                entity_id=contact.entity_id,
                tenant_id=OTHER,
            )

    def test_optimistic_concurrency_rejects_stale_write(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales-1",
            title="Concrete Project",
            source="BuildingConnected",
        )

        first = replace(
            lead,
            description="first edit",
        )

        self.spine.update(
            first,
            tenant_id=TENANT,
            expected_version=lead.version,
            actor_id="sales-1",
            event_type="test.edit",
        )

        stale = replace(
            lead,
            description="stale edit",
        )

        with self.assertRaises(ConcurrencyConflict):
            self.spine.update(
                stale,
                tenant_id=TENANT,
                expected_version=lead.version,
                actor_id="sales-2",
                event_type="test.stale",
            )

    def test_events_are_sequential_per_aggregate(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales-1",
            title="Project",
            source="SAM.gov",
        )

        self.crm.set_lead_next_action(
            tenant_id=TENANT,
            actor_id="sales-1",
            lead_id=lead.entity_id,
            action="Call estimator",
            due_at=now() + timedelta(hours=2),
        )

        events = self.spine.events_for(
            tenant_id=TENANT,
            aggregate_id=lead.entity_id,
        )

        self.assertEqual(
            [event.sequence for event in events],
            [1, 2],
        )


class CRMTests(unittest.TestCase):

    def setUp(self):
        self.spine = InMemoryDataSpine()
        self.crm = GoatCRM(self.spine)

        self.contact = self.crm.create_contact(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales-1",
            display_name="Estimator",
            company_name="General Contractor",
            email="estimator@example.com",
        )

    def test_lead_requires_action_and_due_date_together(self):
        with self.assertRaises(CRMValidationError):
            self.crm.create_lead(
                tenant_id=TENANT,
                business_unit_id=BU,
                actor_id="sales-1",
                title="Project",
                source="Dodge",
                next_action="Call estimator",
            )

    def test_lead_promotes_to_opportunity_without_rekeying(self):
        due = now() + timedelta(days=1)

        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales-1",
            title="Multifamily Project",
            source="BuildingConnected",
            contact_id=self.contact.entity_id,
            owner_user_id="sales-1",
            next_action="Review plans",
            next_action_due_at=due,
        )

        opportunity = self.crm.promote_lead(
            tenant_id=TENANT,
            actor_id="estimator-1",
            lead_id=lead.entity_id,
            estimated_value_cents=500_000_00,
        )

        self.assertEqual(
            opportunity.lead_id,
            lead.entity_id,
        )
        self.assertEqual(
            opportunity.contact_id,
            lead.contact_id,
        )
        self.assertEqual(
            opportunity.source,
            lead.source,
        )
        self.assertEqual(
            opportunity.next_action,
            "Review plans",
        )

    def test_lost_opportunity_requires_reason(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales-1",
            title="Project",
            source="GC Invite",
        )

        opportunity = self.crm.promote_lead(
            tenant_id=TENANT,
            actor_id="sales-1",
            lead_id=lead.entity_id,
        )

        with self.assertRaises(CRMValidationError):
            self.crm.set_opportunity_stage(
                tenant_id=TENANT,
                actor_id="sales-1",
                opportunity_id=opportunity.entity_id,
                stage=OpportunityStage.LOST,
            )

    def test_terminal_stage_cannot_silently_reopen(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales-1",
            title="Project",
            source="GC Invite",
        )

        opportunity = self.crm.promote_lead(
            tenant_id=TENANT,
            actor_id="sales-1",
            lead_id=lead.entity_id,
        )

        lost = self.crm.set_opportunity_stage(
            tenant_id=TENANT,
            actor_id="sales-1",
            opportunity_id=opportunity.entity_id,
            stage=OpportunityStage.LOST,
            lost_reason="price",
        )

        with self.assertRaises(CRMTransitionError):
            self.crm.set_opportunity_stage(
                tenant_id=TENANT,
                actor_id="sales-1",
                opportunity_id=lost.entity_id,
                stage=OpportunityStage.NEGOTIATION,
            )

    def test_won_opportunity_becomes_project(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales-1",
            title="Large Commercial Project",
            source="BuildingConnected",
            contact_id=self.contact.entity_id,
        )

        opportunity = self.crm.promote_lead(
            tenant_id=TENANT,
            actor_id="estimator-1",
            lead_id=lead.entity_id,
            estimated_value_cents=2_000_000_00,
        )

        won = self.crm.set_opportunity_stage(
            tenant_id=TENANT,
            actor_id="president",
            opportunity_id=opportunity.entity_id,
            stage=OpportunityStage.WON,
        )

        project = self.crm.create_project_from_won_opportunity(
            tenant_id=TENANT,
            actor_id="president",
            opportunity_id=won.entity_id,
            project_manager_user_id="pm-1",
        )

        self.assertEqual(
            project.opportunity_id,
            won.entity_id,
        )
        self.assertEqual(
            project.contact_id,
            self.contact.entity_id,
        )
        self.assertEqual(
            project.contract_value_cents,
            2_000_000_00,
        )

    def test_project_cannot_be_created_twice(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales",
            title="Project",
            source="Referral",
        )

        opportunity = self.crm.promote_lead(
            tenant_id=TENANT,
            actor_id="sales",
            lead_id=lead.entity_id,
        )

        won = self.crm.set_opportunity_stage(
            tenant_id=TENANT,
            actor_id="president",
            opportunity_id=opportunity.entity_id,
            stage=OpportunityStage.WON,
        )

        self.crm.create_project_from_won_opportunity(
            tenant_id=TENANT,
            actor_id="president",
            opportunity_id=won.entity_id,
        )

        with self.assertRaises(CRMTransitionError):
            self.crm.create_project_from_won_opportunity(
                tenant_id=TENANT,
                actor_id="president",
                opportunity_id=won.entity_id,
            )


class FollowThroughTests(unittest.TestCase):

    def setUp(self):
        self.spine = InMemoryDataSpine()
        self.crm = GoatCRM(self.spine)
        self.engine = FollowThroughEngine(
            spine=self.spine,
        )

    def test_commitment_requires_completion_evidence(self):
        commitment = self.engine.create_commitment(
            tenant_id=TENANT,
            entity_type="Opportunity",
            entity_id="opp-1",
            owner_user_id="sales-1",
            description="Call GC",
            due_at=now() + timedelta(hours=1),
        )

        with self.assertRaises(ValueError):
            self.engine.complete_commitment(
                commitment_id=commitment.commitment_id,
                actor_id="sales-1",
                evidence="",
            )

    def test_completed_commitment_preserves_evidence(self):
        commitment = self.engine.create_commitment(
            tenant_id=TENANT,
            entity_type="Opportunity",
            entity_id="opp-1",
            owner_user_id="sales-1",
            description="Call GC",
            due_at=now(),
        )

        completed = self.engine.complete_commitment(
            commitment_id=commitment.commitment_id,
            actor_id="sales-1",
            evidence="call://123",
        )

        self.assertEqual(
            completed.status,
            WorkStatus.COMPLETED,
        )
        self.assertEqual(
            completed.completion_evidence,
            "call://123",
        )

    def test_overdue_commitment_escalates_to_owner(self):
        commitment = self.engine.create_commitment(
            tenant_id=TENANT,
            entity_type="Lead",
            entity_id="lead-1",
            owner_user_id="sales-1",
            description="Follow up",
            due_at=now() - timedelta(hours=1),
        )

        level = self.engine.escalation_for(
            commitment,
            now=now(),
        )

        self.assertEqual(
            level,
            EscalationLevel.OWNER,
        )

    def test_overdue_commitment_escalates_to_manager(self):
        commitment = self.engine.create_commitment(
            tenant_id=TENANT,
            entity_type="Lead",
            entity_id="lead-1",
            owner_user_id="sales-1",
            description="Follow up",
            due_at=now() - timedelta(hours=30),
        )

        level = self.engine.escalation_for(
            commitment,
            now=now(),
        )

        self.assertEqual(
            level,
            EscalationLevel.MANAGER,
        )

    def test_long_overdue_commitment_escalates_executive(self):
        commitment = self.engine.create_commitment(
            tenant_id=TENANT,
            entity_type="Lead",
            entity_id="lead-1",
            owner_user_id="sales-1",
            description="Follow up",
            due_at=now() - timedelta(days=5),
        )

        level = self.engine.escalation_for(
            commitment,
            now=now(),
        )

        self.assertEqual(
            level,
            EscalationLevel.EXECUTIVE,
        )

    def test_active_lead_without_next_action_is_flagged(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales",
            title="Concrete Project",
            source="Website",
        )

        findings = self.engine.audit_active_crm(
            tenant_id=TENANT,
            now=now(),
        )

        self.assertTrue(
            any(
                finding.entity_id == lead.entity_id
                and "no next action" in finding.reason
                for finding in findings
            )
        )

    def test_active_opportunity_without_next_action_is_critical(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales",
            title="Electrical Project",
            source="BuildingConnected",
        )

        opportunity = self.crm.promote_lead(
            tenant_id=TENANT,
            actor_id="sales",
            lead_id=lead.entity_id,
        )

        findings = self.engine.audit_active_crm(
            tenant_id=TENANT,
            now=now(),
        )

        matching = [
            finding
            for finding in findings
            if finding.entity_id == opportunity.entity_id
        ]

        self.assertEqual(
            matching[0].severity,
            "critical",
        )

    def test_terminal_opportunity_is_not_flagged_for_followup(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales",
            title="Project",
            source="Referral",
        )

        opportunity = self.crm.promote_lead(
            tenant_id=TENANT,
            actor_id="sales",
            lead_id=lead.entity_id,
        )

        lost = self.crm.set_opportunity_stage(
            tenant_id=TENANT,
            actor_id="sales",
            opportunity_id=opportunity.entity_id,
            stage=OpportunityStage.LOST,
            lost_reason="customer cancelled",
        )

        findings = self.engine.audit_active_crm(
            tenant_id=TENANT,
            now=now(),
        )

        self.assertFalse(
            any(
                finding.entity_id == lost.entity_id
                for finding in findings
            )
        )

    def test_missed_bid_due_date_is_critical(self):
        lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="sales",
            title="Bid Project",
            source="Dodge",
            next_action="Finish estimate",
            next_action_due_at=now() + timedelta(days=1),
        )

        opportunity = self.crm.promote_lead(
            tenant_id=TENANT,
            actor_id="estimator",
            lead_id=lead.entity_id,
            bid_due_at=now() - timedelta(minutes=5),
        )

        findings = self.engine.audit_active_crm(
            tenant_id=TENANT,
            now=now(),
        )

        self.assertTrue(
            any(
                finding.entity_id == opportunity.entity_id
                and finding.reason
                == "bid due date passed without submission"
                and finding.severity == "critical"
                for finding in findings
            )
        )


if __name__ == "__main__":
    unittest.main()
