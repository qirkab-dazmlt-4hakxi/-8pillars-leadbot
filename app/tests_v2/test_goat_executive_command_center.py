import unittest

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from leadbot_v2.goat.access_control import (
    Principal,
    Role,
)
from leadbot_v2.goat.crm.service import (
    GoatCRM,
)
from leadbot_v2.goat.data_spine.models import (
    OpportunityStage,
)
from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
)
from leadbot_v2.goat.executive.command_center import (
    ExecutiveAuthorizationError,
    ExecutiveCommandCenter,
    ExecutivePriority,
    ProjectScenario,
    RecommendationDomain,
)
from leadbot_v2.goat.finance.project_finance import (
    CostCategory,
    ProjectFinanceService,
)
from leadbot_v2.goat.workflow.follow_through import (
    FollowThroughEngine,
)
from leadbot_v2.goat.workforce.sales_ops import (
    AgentProfile,
    SalesOperations,
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
) -> Principal:
    return Principal(
        user_id=user_id,
        tenant_id=TENANT,
        role=role,
        email=f"{user_id}@example.com",
    )


class ExecutiveCommandCenterTests(
    unittest.TestCase
):

    def setUp(self):
        self.spine = InMemoryDataSpine()

        self.crm = GoatCRM(
            self.spine
        )

        self.follow = FollowThroughEngine(
            spine=self.spine
        )

        self.finance = ProjectFinanceService(
            spine=self.spine
        )

        self.sales_ops = SalesOperations(
            spine=self.spine,
            crm=self.crm,
            follow_through=self.follow,
        )

        self.command = ExecutiveCommandCenter(
            spine=self.spine,
            finance=self.finance,
            follow_through=self.follow,
            sales_operations=self.sales_ops,
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
            "security-admin",
            Role.SECURITY_ADMIN,
        )

        # -------------------------------------------------
        # WON PROJECT
        # -------------------------------------------------

        won_lead = self.crm.create_lead(
            tenant_id=TENANT,
            business_unit_id=BU,
            actor_id="president",
            title="Won Concrete Project",
            source="BuildingConnected",
        )

        won_opportunity = (
            self.crm.promote_lead(
                tenant_id=TENANT,
                actor_id="president",
                lead_id=won_lead.entity_id,
                estimated_value_cents=(
                    2_000_000_00
                ),
            )
        )

        won = (
            self.crm.set_opportunity_stage(
                tenant_id=TENANT,
                actor_id="president",
                opportunity_id=(
                    won_opportunity.entity_id
                ),
                stage=OpportunityStage.WON,
            )
        )

        self.project = (
            self.crm
            .create_project_from_won_opportunity(
                tenant_id=TENANT,
                actor_id="president",
                opportunity_id=won.entity_id,
                contract_value_cents=(
                    2_000_000_00
                ),
            )
        )

        # -------------------------------------------------
        # ACTIVE PIPELINE
        # -------------------------------------------------

        pipeline_lead = (
            self.crm.create_lead(
                tenant_id=TENANT,
                business_unit_id=BU,
                actor_id="sales",
                title="Pipeline Electrical Job",
                source="Dodge",
            )
        )

        self.pipeline_opportunity = (
            self.crm.promote_lead(
                tenant_id=TENANT,
                actor_id="sales",
                lead_id=(
                    pipeline_lead.entity_id
                ),
                estimated_value_cents=(
                    500_000_00
                ),
            )
        )

        # -------------------------------------------------
        # FINANCIAL SETUP
        # -------------------------------------------------

        self.finance.register_cost_code(
            principal=self.president,
            tenant_id=TENANT,
            business_unit_id=BU,
            code="03-3000",
            name="Concrete",
            category=CostCategory.MATERIAL,
        )

        self.finance.set_budget(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            amount_cents=1_000_000_00,
        )

        # Intentional forecast deterioration.
        self.finance.set_forecast_to_complete(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            cost_code="03-3000",
            forecast_to_complete_cents=(
                1_500_000_00
            ),
        )

        # Outstanding receivable.
        self.finance.create_ar_invoice(
            principal=self.president,
            tenant_id=TENANT,
            project_id=self.project.entity_id,
            gross_amount_cents=100_000_00,
            retainage_cents=10_000_00,
        )

        # -------------------------------------------------
        # SALES OPERATIONS
        # -------------------------------------------------

        self.sales_ops.create_team(
            principal=self.president,
            team_id="ph-sales",
            business_unit_id=BU,
            name="Philippines Sales",
            manager_user_id="ph-agent",
        )

        self.sales_ops.register_agent(
            principal=self.president,
            profile=AgentProfile(
                user_id="ph-agent",
                tenant_id=TENANT,
                business_unit_id=BU,
                region=(
                    WorkforceRegion.PHILIPPINES
                ),
                level=WorkforceLevel.MANAGER,
                team_id="ph-sales",
                shift=ShiftSchedule(
                    timezone_name=(
                        "Asia/Manila"
                    ),
                    start_hour=0,
                    end_hour=0,
                    weekdays=frozenset({
                        0, 1, 2, 3, 4, 5, 6,
                    }),
                ),
                skills=frozenset({
                    "electrical",
                    "follow_up",
                }),
            ),
        )

    def test_sales_cannot_access_executive_brief(self):
        with self.assertRaises(
            ExecutiveAuthorizationError
        ):
            self.command.build_brief(
                principal=self.sales,
                tenant_id=TENANT,
            )

    def test_security_admin_cannot_access_executive_financial_brief(self):
        with self.assertRaises(
            ExecutiveAuthorizationError
        ):
            self.command.build_brief(
                principal=self.security,
                tenant_id=TENANT,
            )

    def test_president_can_build_brief(self):
        brief = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
        )

        self.assertEqual(
            brief.tenant_id,
            TENANT,
        )

        self.assertGreater(
            len(brief.kpis),
            0,
        )

    def test_every_recommendation_has_evidence(self):
        brief = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
        )

        for recommendation in (
            brief.recommendations
        ):
            self.assertTrue(
                recommendation.evidence
            )

            self.assertTrue(
                recommendation.advisory_only
            )

    def test_every_kpi_has_provenance(self):
        brief = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
        )

        for kpi in brief.kpis:
            self.assertTrue(
                kpi.evidence
            )

    def test_pipeline_value_comes_from_active_opportunities(self):
        brief = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
        )

        value = {
            kpi.code: kpi.value
            for kpi in brief.kpis
        }[
            "active_pipeline_value_cents"
        ]

        self.assertEqual(
            value,
            500_000_00,
        )

    def test_missing_next_action_creates_followthrough_recommendation(self):
        brief = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
        )

        self.assertTrue(
            any(
                item.domain
                == RecommendationDomain
                .FOLLOW_THROUGH
                for item
                in brief.recommendations
            )
        )

    def test_overdue_sales_work_creates_recommendation(self):
        now = datetime.now(
            timezone.utc
        )

        self.sales_ops.assign_work(
            principal=self.president,
            entity_type="Opportunity",
            entity_id=(
                self.pipeline_opportunity
                .entity_id
            ),
            work_type=(
                SalesWorkType.BID_FOLLOW_UP
            ),
            channel=WorkChannel.PHONE,
            assignee_user_id="ph-agent",
            due_at=(
                now - timedelta(days=2)
            ),
        )

        brief = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
            now=now,
        )

        self.assertTrue(
            any(
                item.domain
                == RecommendationDomain.SALES
                and item.priority
                == ExecutivePriority.HIGH
                for item
                in brief.recommendations
            )
        )

    def test_margin_erosion_surfaces_financial_risk(self):
        brief = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
        )

        self.assertTrue(
            any(
                item.domain
                in {
                    RecommendationDomain.FINANCE,
                    RecommendationDomain.MARGIN,
                }
                and item.priority
                in {
                    ExecutivePriority.HIGH,
                    ExecutivePriority.CRITICAL,
                }
                for item
                in brief.recommendations
            )
        )

    def test_outstanding_ar_surfaces_collections_recommendation(self):
        brief = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
        )

        self.assertTrue(
            any(
                item.domain
                == RecommendationDomain
                .COLLECTIONS
                for item
                in brief.recommendations
            )
        )

    def test_positive_revenue_scenario_improves_gp(self):
        result = (
            self.command
            .simulate_project_scenario(
                principal=self.president,
                tenant_id=TENANT,
                project_id=(
                    self.project.entity_id
                ),
                scenario=ProjectScenario(
                    revenue_delta_cents=(
                        100_000_00
                    ),
                ),
            )
        )

        self.assertGreater(
            result.gp_change_cents,
            0,
        )

    def test_cost_increase_reduces_margin(self):
        result = (
            self.command
            .simulate_project_scenario(
                principal=self.president,
                tenant_id=TENANT,
                project_id=(
                    self.project.entity_id
                ),
                scenario=ProjectScenario(
                    cost_delta_cents=(
                        200_000_00
                    ),
                ),
            )
        )

        self.assertLess(
            result.margin_change_bps,
            0,
        )

    def test_scenario_rejects_negative_contract(self):
        with self.assertRaises(ValueError):
            (
                self.command
                .simulate_project_scenario(
                    principal=self.president,
                    tenant_id=TENANT,
                    project_id=(
                        self.project.entity_id
                    ),
                    scenario=ProjectScenario(
                        revenue_delta_cents=(
                            -3_000_000_00
                        ),
                    ),
                )
            )

    def test_recommendation_ids_are_deterministic(self):
        now = datetime.now(
            timezone.utc
        )

        first = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
            now=now,
        )

        second = self.command.build_brief(
            principal=self.president,
            tenant_id=TENANT,
            now=now,
        )

        first_ids = tuple(
            item.recommendation_id
            for item
            in first.recommendations
        )

        second_ids = tuple(
            item.recommendation_id
            for item
            in second.recommendations
        )

        self.assertEqual(
            first_ids,
            second_ids,
        )


if __name__ == "__main__":
    unittest.main()
