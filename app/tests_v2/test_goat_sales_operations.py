import unittest
from datetime import datetime, timedelta, timezone

from leadbot_v2.goat.access_control import (
    AuthorizationEngine,
    Permission,
    Principal,
    ResourceContext,
    Role,
)
from leadbot_v2.goat.crm.service import GoatCRM
from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
    TenantIsolationError,
)
from leadbot_v2.goat.workflow.follow_through import (
    FollowThroughEngine,
)
from leadbot_v2.goat.workforce.sales_ops import (
    AgentProfile,
    CapacityError,
    CompensationPlan,
    QueueStatus,
    SalesOperations,
    SalesOpsAuthorizationError,
    SalesWorkType,
    ShiftSchedule,
    WorkforceLevel,
    WorkforceRegion,
    WorkChannel,
)


TENANT = "twins-development"
BU = "twins-development"


def principal(
    user_id: str,
    role: Role,
    tenant: str = TENANT,
) -> Principal:
    return Principal(
        user_id=user_id,
        tenant_id=tenant,
        role=role,
        email=f"{user_id}@example.com",
    )


class SalesOperationsTests(unittest.TestCase):

    def setUp(self):
        self.spine = InMemoryDataSpine()
        self.crm = GoatCRM(self.spine)
        self.follow = FollowThroughEngine(
            spine=self.spine,
        )

        self.ops = SalesOperations(
            spine=self.spine,
            crm=self.crm,
            follow_through=self.follow,
        )

        self.president = principal(
            "president",
            Role.PRESIDENT,
        )

        self.ph_manager_principal = principal(
            "ph-manager",
            Role.SALES,
        )

        self.ph_agent_principal = principal(
            "ph-agent",
            Role.SALES,
        )

        self.ph_agent_2_principal = principal(
            "ph-agent-2",
            Role.SALES,
        )

        self.texas_agent_principal = principal(
            "tx-agent",
            Role.SALES,
        )

        self.ops.create_team(
            principal=self.president,
            team_id="ph-sales",
            business_unit_id=BU,
            name="Philippines Sales",
            manager_user_id="ph-manager",
        )

        self.ops.create_team(
            principal=self.president,
            team_id="tx-sales",
            business_unit_id=BU,
            name="Texas Sales",
            manager_user_id="tx-manager",
        )

        manila_shift = ShiftSchedule(
            timezone_name="Asia/Manila",
            start_hour=0,
            end_hour=0,
            weekdays=frozenset({
                0, 1, 2, 3, 4, 5, 6,
            }),
        )

        texas_shift = ShiftSchedule(
            timezone_name="America/Chicago",
            start_hour=0,
            end_hour=0,
            weekdays=frozenset({
                0, 1, 2, 3, 4, 5, 6,
            }),
        )

        self.ops.register_agent(
            principal=self.president,
            profile=AgentProfile(
                user_id="ph-manager",
                tenant_id=TENANT,
                business_unit_id=BU,
                region=WorkforceRegion.PHILIPPINES,
                level=WorkforceLevel.MANAGER,
                team_id="ph-sales",
                shift=manila_shift,
                skills=frozenset({
                    "concrete",
                    "electrical",
                    "plumbing",
                }),
            ),
        )

        self.ops.register_agent(
            principal=self.president,
            profile=AgentProfile(
                user_id="ph-agent",
                tenant_id=TENANT,
                business_unit_id=BU,
                region=WorkforceRegion.PHILIPPINES,
                level=WorkforceLevel.AGENT,
                team_id="ph-sales",
                shift=manila_shift,
                skills=frozenset({
                    "concrete",
                    "follow_up",
                }),
            ),
            compensation=CompensationPlan(
                hourly_rate_cents=1300,
                direct_bonus_bps=100,
                team_override_bps=0,
            ),
        )

        self.ops.register_agent(
            principal=self.president,
            profile=AgentProfile(
                user_id="ph-agent-2",
                tenant_id=TENANT,
                business_unit_id=BU,
                region=WorkforceRegion.PHILIPPINES,
                level=WorkforceLevel.AGENT,
                team_id="ph-sales",
                shift=manila_shift,
                skills=frozenset({
                    "concrete",
                    "follow_up",
                }),
                max_open_items=1,
            ),
        )

        self.ops.register_agent(
            principal=self.president,
            profile=AgentProfile(
                user_id="tx-agent",
                tenant_id=TENANT,
                business_unit_id=BU,
                region=WorkforceRegion.TEXAS,
                level=WorkforceLevel.AGENT,
                team_id="tx-sales",
                shift=texas_shift,
                skills=frozenset({
                    "concrete",
                }),
            ),
        )

        self.lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="president",
            title="Concrete Lead",
            source="GOAT Discovery",
            owner_user_id="ph-agent",
            next_action="Contact customer",
            next_action_due_at=(
                datetime.now(timezone.utc)
                + timedelta(hours=2)
            ),
        )

    def test_shift_supports_manila_timezone(self):
        shift = ShiftSchedule(
            timezone_name="Asia/Manila",
            start_hour=0,
            end_hour=0,
            weekdays=frozenset({
                0, 1, 2, 3, 4, 5, 6,
            }),
        )

        self.assertTrue(
            shift.is_on_shift(
                datetime.now(timezone.utc)
            )
        )

    def test_nonexecutive_cannot_create_team(self):
        with self.assertRaises(
            SalesOpsAuthorizationError
        ):
            self.ops.create_team(
                principal=self.ph_agent_principal,
                team_id="illegal-team",
                business_unit_id=BU,
                name="Illegal",
                manager_user_id="ph-agent",
            )

    def test_manager_can_assign_team_agent(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        self.assertEqual(
            item.assigned_to,
            "ph-agent",
        )

    def test_agent_cannot_assign_other_agent(self):
        with self.assertRaises(
            SalesOpsAuthorizationError
        ):
            self.ops.assign_work(
                principal=self.ph_agent_principal,
                entity_type="Lead",
                entity_id=self.lead.entity_id,
                work_type=SalesWorkType.CALL,
                channel=WorkChannel.PHONE,
                assignee_user_id="ph-agent-2",
            )

    def test_assignment_creates_followthrough_commitment(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.FOLLOW_UP,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        commitments = (
            self.follow.open_commitments(
                tenant_id=TENANT
            )
        )

        self.assertTrue(
            any(
                commitment.commitment_id
                == item.commitment_id
                for commitment in commitments
            )
        )

    def test_assigned_agent_can_claim_work(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        claimed = self.ops.claim_work(
            principal=self.ph_agent_principal,
            item_id=item.item_id,
        )

        self.assertEqual(
            claimed.status,
            QueueStatus.IN_PROGRESS,
        )

    def test_wrong_agent_cannot_claim_work(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        with self.assertRaises(
            SalesOpsAuthorizationError
        ):
            self.ops.claim_work(
                principal=self.ph_agent_2_principal,
                item_id=item.item_id,
            )

    def test_completion_requires_evidence(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        with self.assertRaises(ValueError):
            self.ops.complete_work(
                principal=self.ph_agent_principal,
                item_id=item.item_id,
                evidence="",
                disposition="contacted",
            )

    def test_completion_updates_crm_next_action(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        due = (
            datetime.now(timezone.utc)
            + timedelta(days=1)
        )

        completed = self.ops.complete_work(
            principal=self.ph_agent_principal,
            item_id=item.item_id,
            evidence="call://recording-123",
            disposition="customer_requested_callback",
            next_action="Call customer tomorrow",
            next_action_due_at=due,
        )

        refreshed = self.spine.get(
            entity_id=self.lead.entity_id,
            tenant_id=TENANT,
            expected_type=type(self.lead),
        )

        self.assertEqual(
            completed.status,
            QueueStatus.COMPLETED,
        )

        self.assertEqual(
            refreshed.next_action,
            "Call customer tomorrow",
        )

    def test_texas_to_philippines_handoff(self):
        item = self.ops.assign_work(
            principal=self.president,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.FOLLOW_UP,
            channel=WorkChannel.PHONE,
            assignee_user_id="tx-agent",
        )

        handed = self.ops.handoff(
            principal=self.texas_agent_principal,
            item_id=item.item_id,
            new_assignee_user_id="ph-agent",
            reason="Texas shift handoff",
        )

        self.assertEqual(
            handed.region,
            WorkforceRegion.PHILIPPINES,
        )

        self.assertEqual(
            handed.assigned_to,
            "ph-agent",
        )

    def test_cross_tenant_handoff_is_denied(self):
        outsider = principal(
            "outsider",
            Role.SALES,
            tenant="other-tenant",
        )

        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        with self.assertRaises(
            TenantIsolationError
        ):
            self.ops.claim_work(
                principal=outsider,
                item_id=item.item_id,
            )

    def test_agent_cannot_qa_own_work(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        with self.assertRaises(
            SalesOpsAuthorizationError
        ):
            self.ops.submit_quality_review(
                principal=self.ph_agent_principal,
                item_id=item.item_id,
                score=95,
                notes="self review",
            )

    def test_low_qa_score_requires_coaching(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        review = self.ops.submit_quality_review(
            principal=self.ph_manager_principal,
            item_id=item.item_id,
            score=72,
            notes="needs stronger discovery questions",
        )

        self.assertTrue(
            review.coaching_required
        )

    def test_compensation_projection_uses_basis_points(self):
        projection = (
            self.ops.compensation_projection(
                user_id="ph-agent",
                attributable_revenue_cents=100_000_00,
            )
        )

        self.assertEqual(
            projection["direct_bonus_cents"],
            1_000_00,
        )

    def test_sales_role_has_no_financial_read_permission(self):
        engine = AuthorizationEngine()

        decision = engine.authorize(
            self.ph_agent_principal,
            Permission.FINANCIAL_READ,
            ResourceContext(
                tenant_id=TENANT,
            ),
        )

        self.assertFalse(
            decision.allowed
        )

    def test_overdue_work_is_detected(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
            due_at=(
                datetime.now(timezone.utc)
                - timedelta(minutes=1)
            ),
        )

        overdue = self.ops.overdue_items(
            tenant_id=TENANT,
            now=datetime.now(timezone.utc),
        )

        self.assertIn(
            item.item_id,
            {
                work.item_id
                for work in overdue
            },
        )

    def test_queue_orders_high_priority_first(self):
        low = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.EMAIL,
            channel=WorkChannel.EMAIL,
            assignee_user_id="ph-agent",
            priority=10,
        )

        high = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
            priority=90,
        )

        queue = self.ops.queue_for(
            principal=self.ph_agent_principal,
        )

        self.assertEqual(
            queue[0].item_id,
            high.item_id,
        )

        self.assertNotEqual(
            queue[0].item_id,
            low.item_id,
        )

    def test_capacity_limit_is_enforced(self):
        first = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent-2",
        )

        self.assertIsNotNone(first)

        with self.assertRaises(CapacityError):
            self.ops.assign_work(
                principal=self.ph_manager_principal,
                entity_type="Lead",
                entity_id=self.lead.entity_id,
                work_type=SalesWorkType.SMS,
                channel=WorkChannel.SMS,
                assignee_user_id="ph-agent-2",
            )

    def test_performance_snapshot_tracks_completed_work(self):
        item = self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        self.ops.complete_work(
            principal=self.ph_agent_principal,
            item_id=item.item_id,
            evidence="call://abc",
            disposition="qualified",
        )

        performance = self.ops.performance(
            tenant_id=TENANT,
            user_id="ph-agent",
            now=datetime.now(timezone.utc),
        )

        self.assertEqual(
            performance.completed_items,
            1,
        )

    def test_sales_activity_is_written_to_data_spine(self):
        self.ops.assign_work(
            principal=self.ph_manager_principal,
            entity_type="Lead",
            entity_id=self.lead.entity_id,
            work_type=SalesWorkType.CALL,
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
        )

        events = self.spine.events_for(
            tenant_id=TENANT,
            aggregate_id=self.lead.entity_id,
        )

        self.assertTrue(
            any(
                event.event_type
                == "sales.work.assigned"
                for event in events
            )
        )


if __name__ == "__main__":
    unittest.main()
