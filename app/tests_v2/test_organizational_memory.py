import unittest
from dataclasses import replace

from leadbot_v2.goat.continuity.organizational_memory import (
    BusinessContinuityEngine,
    MonitoringContext,
    OrganizationalActivityLedger,
    WorkEventType,
    WorkPatternLearner,
    WorkSource,
)


class OrganizationalMemoryTests(unittest.TestCase):

    def setUp(self):
        self.context = MonitoringContext(
            legitimate_business_purpose=(
                "company operations and continuity"
            ),
            workforce_notice_acknowledged=True,
            company_managed_source=True,
        )

        self.ledger = OrganizationalActivityLedger()

    def test_company_email_can_be_recorded(self):
        event = self.ledger.record(
            context=self.context,
            actor_id="vp-1",
            tenant_id="twins-development",
            business_unit="twins-development",
            event_type=WorkEventType.EMAIL_SENT,
            source=WorkSource.COMPANY_EMAIL,
            summary="Sent project clarification to GC",
            project_id="project-1",
            artifact_ref="email://message-123",
        )

        self.assertEqual(
            event.source,
            WorkSource.COMPANY_EMAIL,
        )

    def test_monitoring_notice_is_required(self):
        bad = MonitoringContext(
            legitimate_business_purpose="continuity",
            workforce_notice_acknowledged=False,
            company_managed_source=True,
        )

        with self.assertRaises(PermissionError):
            self.ledger.record(
                context=bad,
                actor_id="vp-1",
                tenant_id="twins-development",
                business_unit="twins-development",
                event_type=WorkEventType.EMAIL_SENT,
                source=WorkSource.COMPANY_EMAIL,
                summary="test",
            )

    def test_company_managed_source_required(self):
        bad = MonitoringContext(
            legitimate_business_purpose="continuity",
            workforce_notice_acknowledged=True,
            company_managed_source=False,
        )

        with self.assertRaises(PermissionError):
            self.ledger.record(
                context=bad,
                actor_id="vp-1",
                tenant_id="twins-development",
                business_unit="twins-development",
                event_type=WorkEventType.CALL,
                source=WorkSource.COMPANY_PHONE,
                summary="test",
            )

    def test_activity_chain_verifies(self):
        self.ledger.record(
            context=self.context,
            actor_id="vp-1",
            tenant_id="twins-development",
            business_unit="twins-development",
            event_type=WorkEventType.DECISION,
            source=WorkSource.GOAT,
            summary="Approved subcontractor",
            decision_rationale="quality over lowest bid",
        )

        self.assertTrue(self.ledger.verify())

    def test_tampering_is_detected(self):
        self.ledger.record(
            context=self.context,
            actor_id="vp-1",
            tenant_id="twins-development",
            business_unit="twins-development",
            event_type=WorkEventType.DECISION,
            source=WorkSource.GOAT,
            summary="Approved subcontractor",
        )

        event = self.ledger._events[0]

        self.ledger._events[0] = replace(
            event,
            summary="tampered",
        )

        self.assertFalse(self.ledger.verify())

    def test_work_pattern_profile_preserves_process(self):
        self.ledger.record(
            context=self.context,
            actor_id="vp-1",
            tenant_id="twins-development",
            business_unit="twins-development",
            event_type=WorkEventType.APPROVAL,
            source=WorkSource.CRM,
            summary="Approved pursuit",
            opportunity_id="opp-1",
            decision_rationale=(
                "strong GC relationship and margin"
            ),
        )

        profile = WorkPatternLearner.build_profile(
            "vp-1",
            self.ledger.events_for_actor("vp-1"),
        )

        self.assertEqual(profile.event_count, 1)
        self.assertIn("opp-1", profile.opportunity_ids)
        self.assertIn(
            "strong GC relationship and margin",
            profile.recurring_decision_patterns,
        )

    def test_continuity_snapshot_can_be_created(self):
        self.ledger.record(
            context=self.context,
            actor_id="vp-1",
            tenant_id="twins-development",
            business_unit="twins-development",
            event_type=WorkEventType.PROJECT_UPDATE,
            source=WorkSource.PROJECT,
            summary="Updated project",
            project_id="project-42",
            artifact_ref="project://project-42",
        )

        profile = WorkPatternLearner.build_profile(
            "vp-1",
            self.ledger.events_for_actor("vp-1"),
        )

        snapshot = BusinessContinuityEngine.snapshot(
            profile
        )

        self.assertIn(
            "project-42",
            snapshot.open_projects,
        )


if __name__ == "__main__":
    unittest.main()
