import unittest

from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
)
from leadbot_v2.goat.preconstruction.documents.intelligence import (
    RawPage,
)
from leadbot_v2.goat.preconstruction.estimating.workflow import (
    EstimateWorkflowService,
)
from leadbot_v2.goat.preconstruction.orchestrator.whole_plan import (
    PlanTask,
    PlanTrade,
    WholePlanEstimatorOrchestrator,
    WholePlanRequest,
)
from leadbot_v2.goat.preconstruction.regional_costs.engine import (
    TexasMarket,
)


def page(
    number,
    text,
):
    return RawPage(
        page_number=number,
        text=text,
        source_ref=(
            f"plans.pdf#page={number}"
        ),
    )


def request(
    *,
    pages,
    trades,
    city="Dallas",
):
    return WholePlanRequest(
        tenant_id="twins-development",
        business_unit_id="twins-development",
        project_name="GOAT Test Project",
        source_name="plans.pdf",
        pages=tuple(pages),
        city=city,
        requested_trades=tuple(
            trades
        ),
        document_id="doc-test",
    )


class WholePlanRoutingTests(
    unittest.TestCase
):

    def setUp(self):
        self.engine = (
            WholePlanEstimatorOrchestrator()
        )

    def test_structural_routes_to_concrete(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET S2.1\n"
                        "FOUNDATION PLAN\n"
                        '6" SOG',
                    ),
                ),
                trades=(
                    PlanTrade.CONCRETE,
                ),
            )
        )

        self.assertTrue(
            any(
                item.task
                == PlanTask.CONCRETE_TAKEOFF
                for item
                in result.work_items
            )
        )

    def test_civil_routes_to_earthwork(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET C3.1\n"
                        "GRADING PLAN\n"
                        "CUT FILL EXCAVATION",
                    ),
                ),
                trades=(
                    PlanTrade.EARTHWORK,
                ),
            )
        )

        self.assertTrue(
            any(
                item.task
                == PlanTask.EARTHWORK_TAKEOFF
                for item
                in result.work_items
            )
        )

    def test_electrical_routes_correctly(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET E2.1\n"
                        "POWER PLAN\n"
                        "400 AMP SERVICE",
                    ),
                ),
                trades=(
                    PlanTrade.ELECTRICAL,
                ),
            )
        )

        self.assertTrue(
            any(
                item.task
                == PlanTask.ELECTRICAL_TAKEOFF
                for item
                in result.work_items
            )
        )

    def test_plumbing_routes_correctly(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET P2.1\n"
                        "PLUMBING PLAN\n"
                        '4" PVC SANITARY',
                    ),
                ),
                trades=(
                    PlanTrade.PLUMBING,
                ),
            )
        )

        self.assertTrue(
            any(
                item.task
                == PlanTask.PLUMBING_TAKEOFF
                for item
                in result.work_items
            )
        )

    def test_architectural_routes_for_review(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET A1.1\n"
                        "ARCHITECTURAL FLOOR PLAN",
                    ),
                ),
                trades=(
                    PlanTrade.ARCHITECTURAL,
                ),
            )
        )

        self.assertTrue(
            any(
                item.task
                == PlanTask.ARCHITECTURAL_REVIEW
                for item
                in result.work_items
            )
        )

    def test_dallas_market_resolves_dfw(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET S2.1\n"
                        "FOUNDATION PLAN",
                    ),
                ),
                trades=(
                    PlanTrade.CONCRETE,
                ),
                city="Dallas",
            )
        )

        self.assertEqual(
            result.market,
            TexasMarket.DFW,
        )

    def test_houston_market_resolves_houston(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET S2.1\n"
                        "FOUNDATION PLAN",
                    ),
                ),
                trades=(
                    PlanTrade.CONCRETE,
                ),
                city="Houston",
            )
        )

        self.assertEqual(
            result.market,
            TexasMarket.HOUSTON,
        )

    def test_unknown_market_blocks_final_pricing(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET S2.1\n"
                        "FOUNDATION PLAN",
                    ),
                ),
                trades=(
                    PlanTrade.CONCRETE,
                ),
                city="Unknown Texas City",
            )
        )

        self.assertIsNone(
            result.market
        )

        self.assertFalse(
            result.ready_for_final_pricing
        )

    def test_missing_requested_trade_blocks(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET A1.1\n"
                        "ARCHITECTURAL FLOOR PLAN",
                    ),
                ),
                trades=(
                    PlanTrade.ELECTRICAL,
                ),
            )
        )

        self.assertTrue(
            any(
                item.task
                == PlanTask.MISSING_SCOPE
                and item.blocking
                for item
                in result.work_items
            )
        )

    def test_multi_trade_plan_routes_all_scopes(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET S2.1\n"
                        "FOUNDATION PLAN",
                    ),
                    page(
                        2,
                        "SHEET C3.1\n"
                        "GRADING PLAN",
                    ),
                    page(
                        3,
                        "SHEET E2.1\n"
                        "POWER PLAN",
                    ),
                    page(
                        4,
                        "SHEET P2.1\n"
                        "PLUMBING PLAN",
                    ),
                ),
                trades=(
                    PlanTrade.CONCRETE,
                    PlanTrade.EARTHWORK,
                    PlanTrade.ELECTRICAL,
                    PlanTrade.PLUMBING,
                ),
            )
        )

        tasks = {
            item.task
            for item in result.work_items
        }

        self.assertIn(
            PlanTask.CONCRETE_TAKEOFF,
            tasks,
        )

        self.assertIn(
            PlanTask.EARTHWORK_TAKEOFF,
            tasks,
        )

        self.assertIn(
            PlanTask.ELECTRICAL_TAKEOFF,
            tasks,
        )

        self.assertIn(
            PlanTask.PLUMBING_TAKEOFF,
            tasks,
        )

    def test_missing_detail_generates_rfi_work(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET S2.1\n"
                        "FOUNDATION PLAN\n"
                        "SEE DETAIL 4/S5.2",
                    ),
                ),
                trades=(
                    PlanTrade.CONCRETE,
                ),
            )
        )

        self.assertTrue(
            result.rfis
        )

        self.assertTrue(
            any(
                item.task
                == PlanTask.RFI_REVIEW
                for item
                in result.work_items
            )
        )

    def test_existing_detail_resolves(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET S2.1\n"
                        "FOUNDATION PLAN\n"
                        "SEE DETAIL 4/S5.2",
                    ),
                    page(
                        2,
                        "SHEET S5.2\n"
                        "STRUCTURAL DETAILS\n"
                        "DETAIL 4\n"
                        'GB-3 24"x36"',
                    ),
                ),
                trades=(
                    PlanTrade.CONCRETE,
                ),
            )
        )

        self.assertTrue(
            result.detail_resolutions
        )

        self.assertTrue(
            result.detail_resolutions[0]
            .resolved
        )

    def test_discipline_counts_preserved(self):
        result = self.engine.analyze(
            request(
                pages=(
                    page(
                        1,
                        "SHEET S2.1\n"
                        "FOUNDATION PLAN",
                    ),
                    page(
                        2,
                        "SHEET S5.1\n"
                        "STRUCTURAL DETAILS",
                    ),
                ),
                trades=(
                    PlanTrade.CONCRETE,
                ),
            )
        )

        counts = dict(
            result.discipline_counts
        )

        self.assertEqual(
            counts["structural"],
            2,
        )


class WholePlanEstimateBridgeTests(
    unittest.TestCase
):

    def test_analysis_initializes_goat_estimate(self):
        engine = (
            WholePlanEstimatorOrchestrator()
        )

        req = request(
            pages=(
                page(
                    1,
                    "SHEET S2.1\n"
                    "FOUNDATION PLAN",
                ),
            ),
            trades=(
                PlanTrade.CONCRETE,
            ),
        )

        analysis = engine.analyze(
            req
        )

        spine = InMemoryDataSpine()

        workflow = EstimateWorkflowService(
            spine=spine
        )

        estimate = (
            engine.initialize_estimate(
                request=req,
                analysis=analysis,
                workflow=workflow,
                actor_id="estimator",
            )
        )

        self.assertEqual(
            estimate.project_name,
            "GOAT Test Project",
        )

        self.assertGreaterEqual(
            len(
                estimate.qualifications
            ),
            2,
        )

    def test_blocking_rfi_enters_estimate(self):
        engine = (
            WholePlanEstimatorOrchestrator()
        )

        req = request(
            pages=(
                page(
                    1,
                    "SHEET S2.1\n"
                    "FOUNDATION PLAN\n"
                    "SEE DETAIL 4/S5.2",
                ),
            ),
            trades=(
                PlanTrade.CONCRETE,
            ),
        )

        analysis = engine.analyze(
            req
        )

        workflow = (
            EstimateWorkflowService(
                spine=(
                    InMemoryDataSpine()
                )
            )
        )

        estimate = (
            engine.initialize_estimate(
                request=req,
                analysis=analysis,
                workflow=workflow,
                actor_id="estimator",
            )
        )

        self.assertTrue(
            estimate.rfi_effects
        )

        self.assertTrue(
            any(
                effect.blocking
                for effect
                in estimate.rfi_effects
            )
        )

    def test_market_is_written_to_qualification(self):
        engine = (
            WholePlanEstimatorOrchestrator()
        )

        req = request(
            pages=(
                page(
                    1,
                    "SHEET E2.1\n"
                    "POWER PLAN",
                ),
            ),
            trades=(
                PlanTrade.ELECTRICAL,
            ),
            city="Houston",
        )

        analysis = engine.analyze(
            req
        )

        workflow = (
            EstimateWorkflowService(
                spine=(
                    InMemoryDataSpine()
                )
            )
        )

        estimate = (
            engine.initialize_estimate(
                request=req,
                analysis=analysis,
                workflow=workflow,
                actor_id="estimator",
            )
        )

        text = "\n".join(
            estimate.qualifications
        )

        self.assertIn(
            "houston",
            text,
        )


if __name__ == "__main__":
    unittest.main()
