import unittest

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from leadbot_v2.goat.preconstruction.bid_packages.control import (
    BidPackageControlService,
)

from leadbot_v2.goat.preconstruction.command_center.engine import (
    BidCommandCenter,
    BidCaseState,
)

from leadbot_v2.goat.preconstruction.opportunities.engine import (
    CapacitySnapshot,
    ContactKind,
    ContactPath,
    DecisionDisposition,
    FindingSeverity,
    FollowUpKind,
    OpportunityBlocked,
    OpportunityConfig,
    OpportunityEvidence,
    OpportunityIntelligenceService,
    OpportunitySource,
    OpportunityState,
    RelationshipProfile,
    TradeScope,
)


UTC = timezone.utc


def now():
    return datetime(
        2026,
        8,
        15,
        17,
        0,
        tzinfo=UTC,
    )


def config():
    return OpportunityConfig(
        enabled_trades=frozenset(
            {
                TradeScope.CONCRETE,
                TradeScope.EARTHWORK,
                TradeScope.ELECTRICAL,
                TradeScope.PLUMBING,
                TradeScope.MEP,
            }
        ),
        preferred_cities=frozenset(
            {
                "Dallas",
                "Frisco",
                "Prosper",
                "Denton",
                "Aubrey",
            }
        ),
        allowed_cities=frozenset(
            {
                "Dallas",
                "Frisco",
                "Prosper",
                "Denton",
                "Aubrey",
                "Fort Worth",
                "McKinney",
                "Celina",
                "Houston",
                "Austin",
            }
        ),
        min_bid_score=70.0,
        min_review_score=50.0,
    )


def verified_contact():
    return ContactPath(
        kind=ContactKind.EMAIL,
        value="estimating@example.com",
        reachable=True,
        verified=True,
        public=True,
        source_ref="invite:1",
    )


def evidence(
    confidence=0.95,
):
    return OpportunityEvidence(
        evidence_id="e1",
        label="GC invitation",
        source_ref="invite:1",
        observed_at=now(),
        confidence=confidence,
    )


def capacity():
    return CapacitySnapshot(
        estimator_hours_available=80.0,
        estimator_hours_committed=20.0,
        operations_capacity_percent=60.0,
        active_bid_count=4,
        max_active_bid_count=20,
    )


def relationship():
    return RelationshipProfile(
        organization_name="Excellent GC",
        invite_count=12,
        bid_count=8,
        win_count=4,
        loss_count=4,
        paid_projects=3,
        payment_issue_count=0,
        response_count=10,
        positive_relationship_signals=4,
        negative_relationship_signals=0,
    )


def service(
    *,
    integrate=False,
):
    if not integrate:
        return (
            OpportunityIntelligenceService(
                config=config()
            )
        )

    package_control = (
        BidPackageControlService()
    )

    command_center = (
        BidCommandCenter(
            package_control=(
                package_control
            )
        )
    )

    return (
        OpportunityIntelligenceService(
            config=config(),
            package_control=(
                package_control
            ),
            command_center=(
                command_center
            ),
        )
    )


def ingest_good(
    svc,
    *,
    source=(
        OpportunitySource
        .BUILDING_CONNECTED
    ),
    due_hours=120,
    bid=1_000_000,
    direct=750_000,
):
    return svc.ingest(
        tenant_id="tenant",
        business_unit_id="twins",
        source=source,
        source_opportunity_id="BC-100",
        project_name="Medical Office",
        city="Dallas",
        county="Dallas",
        state_region="TX",
        gc_name="Excellent GC",
        client_name="Owner",
        requested_trades=(
            TradeScope.CONCRETE,
            TradeScope.ELECTRICAL,
        ),
        scope_summary=(
            "Structural concrete and "
            "electrical construction."
        ),
        due_at=(
            now()
            + timedelta(
                hours=due_hours
            )
        ),
        estimated_bid_cents=bid,
        estimated_direct_cost_cents=direct,
        pursuit_hours_estimate=12.0,
        contacts=(
            verified_contact(),
        ),
        evidence=(
            evidence(),
            OpportunityEvidence(
                evidence_id="e2",
                label="Plan package",
                source_ref="plans:1",
                observed_at=now(),
                confidence=0.96,
            ),
            OpportunityEvidence(
                evidence_id="e3",
                label="Scope sheet",
                source_ref="scope:1",
                observed_at=now(),
                confidence=0.94,
            ),
        ),
        actor_id="system",
    )


class IntakeTests(
    unittest.TestCase
):

    def test_ingest_creates_discovered_opportunity(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        self.assertEqual(
            opp.state,
            OpportunityState.DISCOVERED,
        )

        self.assertEqual(
            opp.gc_name,
            "Excellent GC",
        )

    def test_source_id_is_idempotent(self):
        svc = service()

        first = ingest_good(
            svc
        )

        second = ingest_good(
            svc
        )

        self.assertEqual(
            first.opportunity_id,
            second.opportunity_id,
        )

    def test_semantic_duplicate_is_collapsed(self):
        svc = service()

        first = ingest_good(
            svc
        )

        second = svc.ingest(
            tenant_id="tenant",
            business_unit_id="twins",
            source=(
                OpportunitySource
                .PUBLIC_WEB
            ),
            project_name=(
                "MEDICAL OFFICE"
            ),
            city="Dallas",
            county="Dallas",
            state_region="TX",
            gc_name="Excellent GC",
            client_name="Owner",
            requested_trades=(
                TradeScope.CONCRETE,
            ),
            scope_summary="Concrete",
            due_at=(
                now()
                + timedelta(
                    hours=120
                )
            ),
            contacts=(
                verified_contact(),
            ),
            actor_id="system",
        )

        self.assertEqual(
            first.opportunity_id,
            second.opportunity_id,
        )


class DecisionTests(
    unittest.TestCase
):

    def test_strong_opportunity_recommends_bid(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=(
                relationship()
            ),
            capacity=(
                capacity()
            ),
            as_of=now(),
        )

        self.assertEqual(
            decision.disposition,
            DecisionDisposition.BID,
        )

        self.assertGreaterEqual(
            decision.score,
            70.0,
        )

    def test_missing_contact_blocks(self):
        svc = service()

        opp = svc.ingest(
            tenant_id="tenant",
            business_unit_id="twins",
            source=(
                OpportunitySource
                .PUBLIC_WEB
            ),
            project_name="Project X",
            city="Dallas",
            state_region="TX",
            gc_name="GC",
            requested_trades=(
                TradeScope.CONCRETE,
            ),
            scope_summary="Concrete",
            due_at=(
                now()
                + timedelta(
                    days=5
                )
            ),
            estimated_bid_cents=500_000,
            estimated_direct_cost_cents=350_000,
            contacts=(),
            evidence=(
                evidence(),
            ),
            actor_id="system",
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            capacity=capacity(),
            relationship=relationship(),
            as_of=now(),
        )

        self.assertEqual(
            decision.disposition,
            DecisionDisposition.BLOCKED,
        )

        self.assertIn(
            "CONTACT_PATH_UNRESOLVED",
            {
                item.code
                for item
                in decision.blockers
            },
        )

    def test_missing_pricing_remains_reviewable(self):
        svc = service()

        opp = ingest_good(
            svc,
            bid=None,
            direct=None,
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=(
                relationship()
            ),
            capacity=capacity(),
            as_of=now(),
        )

        self.assertNotEqual(
            decision.disposition,
            DecisionDisposition.BID,
        )

        self.assertIsNone(
            decision
            .economics
            .expected_value_cents
        )

    def test_negative_margin_blocks(self):
        svc = service()

        opp = ingest_good(
            svc,
            bid=500_000,
            direct=600_000,
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        self.assertEqual(
            decision.disposition,
            DecisionDisposition.BLOCKED,
        )

        self.assertIn(
            "NONPOSITIVE_GROSS_PROFIT",
            {
                item.code
                for item
                in decision.blockers
            },
        )

    def test_expired_bid_blocks(self):
        svc = service()

        opp = ingest_good(
            svc,
            due_hours=-1,
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        self.assertIn(
            "BID_DUE_DATE_PASSED",
            {
                item.code
                for item
                in decision.blockers
            },
        )

    def test_trade_mismatch_blocks(self):
        svc = service()

        opp = svc.ingest(
            tenant_id="tenant",
            business_unit_id="twins",
            source=(
                OpportunitySource
                .DIRECT_GC
            ),
            project_name="Landscape Only",
            city="Dallas",
            state_region="TX",
            gc_name="GC",
            requested_trades=(
                TradeScope.OTHER,
            ),
            scope_summary="Landscape",
            due_at=(
                now()
                + timedelta(
                    days=5
                )
            ),
            contacts=(
                verified_contact(),
            ),
            evidence=(
                evidence(),
            ),
            actor_id="system",
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            capacity=capacity(),
            as_of=now(),
        )

        self.assertIn(
            "NO_ENABLED_TRADE_MATCH",
            {
                item.code
                for item
                in decision.blockers
            },
        )

    def test_capacity_shortfall_generates_review(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        constrained = (
            CapacitySnapshot(
                estimator_hours_available=40,
                estimator_hours_committed=38,
                operations_capacity_percent=95,
                active_bid_count=19,
                max_active_bid_count=20,
            )
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=constrained,
            as_of=now(),
        )

        self.assertIn(
            "ESTIMATING_CAPACITY_SHORTFALL",
            {
                item.code
                for item
                in decision.findings
            },
        )


class EconomicTests(
    unittest.TestCase
):

    def test_expected_value_is_calculated(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        economics = (
            decision.economics
        )

        self.assertEqual(
            economics.gross_profit_cents,
            250_000,
        )

        self.assertIsNotNone(
            economics
            .expected_value_cents
        )

        self.assertGreater(
            economics
            .modeled_win_probability,
            0,
        )

    def test_pursuit_cost_is_in_expected_value(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        self.assertGreater(
            decision
            .economics
            .pursuit_cost_cents,
            0,
        )


class FollowThroughTests(
    unittest.TestCase
):

    def test_bid_creates_plan_request_task(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        tasks = (
            svc.schedule_follow_through(
                opportunity_id=(
                    opp.opportunity_id
                ),
                actor_id="system",
                as_of=now(),
            )
        )

        self.assertIn(
            FollowUpKind.REQUEST_PLANS,
            {
                task.kind
                for task
                in tasks
            },
        )

    def test_missing_contact_creates_contact_task(self):
        svc = service()

        opp = svc.ingest(
            tenant_id="tenant",
            business_unit_id="twins",
            source=(
                OpportunitySource
                .PUBLIC_WEB
            ),
            project_name="No Contact",
            city="Dallas",
            state_region="TX",
            requested_trades=(
                TradeScope.CONCRETE,
            ),
            scope_summary="Concrete",
            due_at=(
                now()
                + timedelta(
                    days=3
                )
            ),
            contacts=(),
            actor_id="system",
        )

        tasks = (
            svc.schedule_follow_through(
                opportunity_id=(
                    opp.opportunity_id
                ),
                actor_id="system",
                as_of=now(),
            )
        )

        self.assertIn(
            FollowUpKind.CONTACT_GC,
            {
                task.kind
                for task
                in tasks
            },
        )

    def test_follow_through_is_idempotent(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        first = (
            svc.schedule_follow_through(
                opportunity_id=(
                    opp.opportunity_id
                ),
                actor_id="system",
                as_of=now(),
            )
        )

        second = (
            svc.schedule_follow_through(
                opportunity_id=(
                    opp.opportunity_id
                ),
                actor_id="system",
                as_of=now(),
            )
        )

        self.assertTrue(
            first
        )

        self.assertEqual(
            second,
            (),
        )

    def test_task_completion(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        task = (
            svc.schedule_follow_through(
                opportunity_id=(
                    opp.opportunity_id
                ),
                actor_id="system",
                as_of=now(),
            )[0]
        )

        completed = (
            svc.complete_task(
                task_id=(
                    task.task_id
                ),
                actor_id="estimator",
            )
        )

        self.assertTrue(
            completed.completed
        )


class PromotionTests(
    unittest.TestCase
):

    def test_strong_opportunity_promotes_to_bid_package(self):
        svc = service(
            integrate=True
        )

        opp = ingest_good(
            svc
        )

        decision = svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        self.assertEqual(
            decision.disposition,
            DecisionDisposition.BID,
        )

        package, case = (
            svc.promote_to_bid(
                opportunity_id=(
                    opp.opportunity_id
                ),
                actor_id="estimator",
            )
        )

        updated = svc.get(
            opp.opportunity_id
        )

        self.assertEqual(
            updated.state,
            OpportunityState.PROMOTED,
        )

        self.assertEqual(
            updated
            .promoted_package_id,
            package.package_id,
        )

        self.assertEqual(
            updated
            .promoted_case_id,
            case.case_id,
        )

        # Correct behavior: package contains no plans yet,
        # therefore command center begins blocked.
        self.assertEqual(
            case.state,
            BidCaseState.BLOCKED,
        )

    def test_review_cannot_auto_promote(self):
        svc = service(
            integrate=True
        )

        opp = ingest_good(
            svc,
            bid=None,
            direct=None,
        )

        svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        with self.assertRaises(
            OpportunityBlocked
        ):
            svc.promote_to_bid(
                opportunity_id=(
                    opp.opportunity_id
                ),
                actor_id="estimator",
            )

    def test_promotion_is_idempotent(self):
        svc = service(
            integrate=True
        )

        opp = ingest_good(
            svc
        )

        svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        first_package, first_case = (
            svc.promote_to_bid(
                opportunity_id=(
                    opp.opportunity_id
                ),
                actor_id="estimator",
            )
        )

        second_package, second_case = (
            svc.promote_to_bid(
                opportunity_id=(
                    opp.opportunity_id
                ),
                actor_id="estimator",
            )
        )

        self.assertEqual(
            first_package.package_id,
            second_package.package_id,
        )

        self.assertEqual(
            first_case.case_id,
            second_case.case_id,
        )


class PortfolioTests(
    unittest.TestCase
):

    def test_portfolio_contains_decision(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        item = svc.portfolio()[0]

        self.assertEqual(
            item.opportunity_id,
            opp.opportunity_id,
        )

        self.assertIsNotNone(
            item.score
        )

        self.assertIsNotNone(
            item.expected_value_cents
        )


class AuditTests(
    unittest.TestCase
):

    def test_audit_chain_verifies(self):
        svc = service()

        opp = ingest_good(
            svc
        )

        svc.evaluate(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="estimator",
            relationship=relationship(),
            capacity=capacity(),
            as_of=now(),
        )

        svc.schedule_follow_through(
            opportunity_id=(
                opp.opportunity_id
            ),
            actor_id="system",
            as_of=now(),
        )

        self.assertTrue(
            svc.verify_audit(
                opp.opportunity_id
            )
        )


if __name__ == "__main__":
    unittest.main()
